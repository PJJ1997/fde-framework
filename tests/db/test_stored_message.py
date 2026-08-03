import unittest

from pydantic import ValidationError

from db.models import (
    FileContent,
    ImageContent,
    JsonContent,
    StoredMessage,
    StoredToolCall,
    TextContent,
)


class StoredMessageTests(unittest.TestCase):
    def test_supports_text_image_file_and_json_content(self):
        message = StoredMessage(
            message_type="user",
            content=[
                TextContent(text="分析附件"),
                ImageContent(
                    url="https://example.test/image.png",
                    mime_type="image/png",
                ),
                ImageContent(
                    data="aW1hZ2U=",
                    mime_type="image/png",
                ),
                FileContent(
                    file_id="file-1",
                    filename="report.pdf",
                    mime_type="application/pdf",
                ),
                JsonContent(data={"page": 1, "labels": ["invoice"]}),
            ],
        )

        restored = StoredMessage.model_validate_json(
            message.model_dump_json()
        )

        self.assertEqual(restored.content[0].type, "text")
        self.assertEqual(restored.content[1].type, "image")
        self.assertEqual(restored.content[3].type, "file")
        self.assertEqual(restored.content[4].type, "json")

    def test_rejects_image_or_file_without_reference(self):
        with self.assertRaises(ValidationError):
            ImageContent(mime_type="image/png")
        with self.assertRaises(ValidationError):
            FileContent(filename="report.pdf")

    def test_supports_assistant_tool_calls_and_tool_results(self):
        assistant = StoredMessage(
            message_type="assistant",
            tool_calls=[
                StoredToolCall(
                    id="call-1",
                    name="get_order",
                    arguments={"order_id": "ORD-1004"},
                )
            ],
        )
        tool = StoredMessage(
            message_type="tool",
            tool_call_id="call-1",
            name="get_order",
            content=[
                JsonContent(data={
                    "order_id": "ORD-1004",
                    "status": "created",
                })
            ],
        )

        self.assertEqual(assistant.tool_calls[0].name, "get_order")
        self.assertEqual(tool.tool_call_id, "call-1")

    def test_rejects_invalid_message_type_combinations(self):
        invalid_cases = [
            {
                "message_type": "user",
                "tool_calls": [{
                    "id": "call-1",
                    "name": "get_order",
                    "arguments": {},
                }],
            },
            {
                "message_type": "assistant",
                "tool_call_id": "call-1",
            },
            {
                "message_type": "tool",
                "content": [{"type": "text", "text": "done"}],
            },
            {
                "message_type": "system",
                "content": [{"type": "text", "text": "prompt"}],
            },
        ]

        for payload in invalid_cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    StoredMessage.model_validate(payload)

    def test_rejects_empty_tool_identity_and_non_json_metadata(self):
        with self.assertRaises(ValidationError):
            StoredToolCall(id="", name="get_order", arguments={})
        with self.assertRaises(ValidationError):
            StoredMessage(
                message_type="user",
                metadata={"unsupported": object()},
            )


if __name__ == "__main__":
    unittest.main()
