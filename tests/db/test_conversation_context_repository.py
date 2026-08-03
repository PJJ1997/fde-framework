import tempfile
import unittest
from pathlib import Path

from db.database import Database
from db.repositories import ConversationContextRepository
# Schema is now part of Database class


class ConversationContextRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(
            str(Path(self.temp_dir.name) / "chat.db")
        )
        self.database.initialize_schema()
        self.repository = ConversationContextRepository(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_upsert_increments_version_and_preserves_message_id(self):
        first_version = self.repository.upsert(
            session_id="session-1",
            context_json='{"summary":"first"}',
            schema_version="1.0",
            last_message_id=11,
        )
        second_version = self.repository.upsert(
            session_id="session-1",
            context_json='{"summary":"second"}',
            schema_version="1.1",
        )

        restored = self.repository.get("session-1")

        self.assertEqual(first_version, 1)
        self.assertEqual(second_version, 2)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.context_json, '{"summary":"second"}')
        self.assertEqual(restored.schema_version, "1.1")
        self.assertEqual(restored.context_version, 2)
        self.assertEqual(restored.last_message_id, 11)

    def test_get_missing_and_delete(self):
        self.assertIsNone(self.repository.get("missing"))
        self.repository.upsert(
            session_id="session-1",
            context_json="{}",
            schema_version="1.0",
        )

        self.assertEqual(self.repository.delete("session-1"), 1)
        self.assertIsNone(self.repository.get("session-1"))
        self.assertEqual(self.repository.delete("session-1"), 0)


if __name__ == "__main__":
    unittest.main()
