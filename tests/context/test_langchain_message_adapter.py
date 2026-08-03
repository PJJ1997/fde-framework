import unittest

from langchain_core.messages import (
    AIMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from context.adapters import LangChainMessageAdapter
from db.errors import UnsupportedStoredMessageError


class LangChainMessageAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = LangChainMessageAdapter()

    def test_round_trips_human_text(self):
        stored = self.adapter.to_stored(HumanMessage(content="hello"))
        restored = self.adapter.to_langchain(stored)

        self.assertEqual(stored.message_type, "user")
        self.assertEqual(stored.content[0].text, "hello")
        self.assertIsInstance(restored, HumanMessage)
        self.assertEqual(restored.content, "hello")

    def test_round_trips_human_text_and_image(self):
        original = HumanMessage(content=[
            {"type": "text", "text": "分析图片"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.test/image.png",
                    "detail": "high",
                },
            },
        ])

        stored = self.adapter.to_stored(original)
        restored = self.adapter.to_langchain(stored)

        self.assertEqual(stored.content[1].type, "image")
        self.assertEqual(stored.content[1].detail, "high")
        self.assertEqual(
            restored.content[1]["image_url"]["url"],
            "https://example.test/image.png",
        )

    def test_round_trips_ai_text_and_tool_calls(self):
        original = AIMessage(
            content="正在查询",
            tool_calls=[{
                "id": "call-1",
                "name": "get_order",
                "args": {"order_id": "ORD-1004"},
                "type": "tool_call",
            }],
        )

        stored = self.adapter.to_stored(original)
        restored = self.adapter.to_langchain(stored)

        self.assertEqual(stored.message_type, "assistant")
        self.assertEqual(stored.tool_calls[0].arguments, {
            "order_id": "ORD-1004",
        })
        self.assertIsInstance(restored, AIMessage)
        self.assertEqual(restored.tool_calls[0]["name"], "get_order")

    def test_round_trips_tool_text_and_json_results(self):
        text_message = ToolMessage(
            content="查询成功",
            tool_call_id="call-1",
            name="get_order",
        )
        json_message = ToolMessage(
            content=[{
                "type": "json",
                "data": {"order_id": "ORD-1004"},
            }],
            tool_call_id="call-2",
            name="get_order",
        )

        stored_text = self.adapter.to_stored(text_message)
        stored_json = self.adapter.to_stored(json_message)
        restored_json = self.adapter.to_langchain(stored_json)

        self.assertEqual(stored_text.content[0].type, "text")
        self.assertEqual(stored_json.content[0].type, "json")
        self.assertIsInstance(restored_json, ToolMessage)
        self.assertEqual(
            restored_json.content[0]["data"]["order_id"],
            "ORD-1004",
        )

    def test_rejects_system_unknown_blocks_and_invalid_tool_calls(self):
        invalid_messages = [
            SystemMessage(content="system prompt"),
            ChatMessage(role="critic", content="review"),
            HumanMessage(content=[{"type": "audio", "url": "audio.mp3"}]),
            AIMessage(
                content="",
                invalid_tool_calls=[{
                    "id": "bad-1",
                    "name": "broken",
                    "args": "{",
                    "error": "invalid",
                    "type": "invalid_tool_call",
                }],
            ),
        ]

        for message in invalid_messages:
            with self.subTest(message=type(message).__name__):
                with self.assertRaises(UnsupportedStoredMessageError):
                    self.adapter.to_stored(message)


if __name__ == "__main__":
    unittest.main()
