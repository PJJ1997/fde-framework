import sqlite3
import tempfile
import unittest
from pathlib import Path

from agents.planner_executor.schemas import StepResult
from context.manager import ContextManager
from context.structured import StructuredConversationContext


class ContextStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "chat.db")
        self.manager = ContextManager(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manager_composes_table_specific_repositories(self):
        self.assertIsNotNone(self.manager.message_repository)
        self.assertIsNotNone(
            self.manager.conversation_context_repository
        )

    def test_save_load_and_version_increment(self):
        first = StructuredConversationContext(summary="first")
        self.assertEqual(
            self.manager.save_structured_context("session-1", first, 4),
            1,
        )

        second = first.model_copy(update={"summary": "second"})
        self.assertEqual(
            self.manager.save_structured_context("session-1", second, 5),
            2,
        )

        restored = self.manager.get_structured_context("session-1")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.summary, "second")

    def test_invalid_stored_json_is_treated_as_missing(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_contexts (
                    session_id, context_json, schema_version,
                    context_version, last_message_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("session-1", "{invalid", "1.0", 1, None),
            )

        self.assertIsNone(
            self.manager.get_structured_context("session-1")
        )

    def test_clear_session_removes_messages_and_context(self):
        self.manager.save_user_message("session-1", "hello")
        self.manager.save_structured_context(
            "session-1", StructuredConversationContext()
        )

        self.manager.clear_session("session-1")

        self.assertIsNone(
            self.manager.get_structured_context("session-1")
        )
        self.assertEqual(
            self.manager.get_session_history("session-1"), []
        )

    def test_record_tool_facts_keeps_only_successful_results(self):
        self.manager.save_structured_context(
            "session-1",
            StructuredConversationContext(),
            last_message_id=11,
        )

        updated = self.manager.record_tool_facts("session-1", [
            StepResult(
                step_id="step_1",
                tool_name="update_order",
                success=True,
                result={
                    "order": {
                        "order_id": "ORD-1001",
                        "price": 80,
                    }
                },
                message="updated",
            ),
            StepResult(
                step_id="step_2",
                tool_name="missing_tool",
                success=False,
                result={"error": "failed"},
                message="failed",
            ),
        ])

        self.assertIsNotNone(updated)
        self.assertEqual(len(updated.tool_facts), 1)
        self.assertEqual(updated.tool_facts[0].tool, "update_order")
        self.assertEqual(
            updated.tool_facts[0].data["order"]["price"], 80
        )
        stored = self.manager.conversation_context_repository.get(
            "session-1"
        )
        self.assertEqual(stored.last_message_id, 11)


if __name__ == "__main__":
    unittest.main()
