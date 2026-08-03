import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from context.manager import ContextManager
from db.models import ImageContent, Message, StoredMessage, TextContent


class MessageHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = ContextManager(
            str(Path(self.temp_dir.name) / "chat.db")
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_saves_stable_history_and_skips_system_messages(self):
        self.manager.save_user_message("session-1", "hello")
        self.manager.save_agent_messages("session-1", [
            SystemMessage(content="runtime prompt"),
            AIMessage(
                content="querying",
                tool_calls=[{
                    "id": "call-1",
                    "name": "get_order",
                    "args": {"order_id": "ORD-1004"},
                    "type": "tool_call",
                }],
            ),
            ToolMessage(
                content="done",
                tool_call_id="call-1",
                name="get_order",
            ),
        ])

        history = self.manager.get_session_history("session-1")

        self.assertEqual(
            [message.message_type for message in history],
            ["user", "assistant", "tool"],
        )
        self.assertEqual(history[1].tool_calls[0].name, "get_order")
        self.assertIsNotNone(
            self.manager.get_last_message_id("session-1")
        )

    def test_build_restores_langchain_multimodal_history(self):
        stored = StoredMessage(
            message_type="user",
            content=[
                TextContent(text="分析图片"),
                ImageContent(
                    url="https://example.test/image.png",
                    mime_type="image/png",
                ),
            ],
        )
        self.manager.message_repository.save(
            Message.from_stored("session-1", stored)
        )

        messages = self.manager.build(
            session_id="session-1",
            user_input="",
        )

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], HumanMessage)
        self.assertEqual(
            messages[0].content[1]["image_url"]["url"],
            "https://example.test/image.png",
        )

    def test_get_conversations_returns_only_displayable_text(self):
        self.manager.save_user_message("session-1", "hello")
        self.manager.save_agent_messages("session-1", [
            AIMessage(content=[
                {"type": "text", "text": "order"},
                {"type": "text", "text": " created"},
            ]),
            ToolMessage(content="internal", tool_call_id="call-1"),
        ])

        conversations = self.manager.get_conversations("session-1")

        self.assertEqual(
            [(item["role"], item["content"]) for item in conversations],
            [
                ("user", "hello"),
                ("assistant", "order created"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
