import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.database import Database
from db.errors import MessageIntegrityError
from db.models import Message, StoredMessage, TextContent
from db.repositories import MessageRepository
# Schema is now part of Database class


class MessageRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(
            str(Path(self.temp_dir.name) / "chat.db")
        )
        self.database.initialize_schema()
        self.repository = MessageRepository(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _message(session_id: str, text: str) -> Message:
        return Message.from_stored(
            session_id,
            StoredMessage(
                message_type="user",
                content=[TextContent(text=text)],
            ),
        )

    def test_save_restore_and_order_by_id(self):
        first_id = self.repository.save(
            self._message("session-1", "first")
        )
        second_id = self.repository.save(
            self._message("session-1", "second")
        )

        oldest = self.repository.find_by_session("session-1")
        newest = self.repository.find_by_session(
            "session-1",
            newest_first=True,
        )

        self.assertGreater(second_id, first_id)
        self.assertEqual(
            [record.to_stored().content[0].text for record in oldest],
            ["first", "second"],
        )
        self.assertEqual(
            [record.to_stored().content[0].text for record in newest],
            ["second", "first"],
        )

    def test_limit_delete_and_session_list(self):
        for session_id, text in (
            ("session-b", "one"),
            ("session-a", "two"),
            ("session-a", "three"),
        ):
            self.repository.save(self._message(session_id, text))

        self.assertEqual(
            len(self.repository.find_by_session("session-a", limit=1)),
            1,
        )
        with self.assertRaises(ValueError):
            self.repository.find_by_session("session-a", limit=-1)
        self.assertEqual(
            self.repository.list_session_ids(),
            ["session-a", "session-b"],
        )
        self.assertIsNotNone(
            self.repository.get_last_id("session-a")
        )
        self.assertEqual(
            self.repository.delete_by_session("session-a"),
            2,
        )
        self.assertIsNone(
            self.repository.get_last_id("session-a")
        )

    def test_rejects_type_version_and_payload_corruption(self):
        record = self._message("session-1", "hello")
        self.repository.save(record)

        corruptions = [
            ("message_type", "assistant"),
            ("schema_version", 99),
            ("payload_json", "{invalid"),
        ]
        for column, value in corruptions:
            with self.subTest(column=column):
                with self.database.connect() as connection:
                    connection.execute(
                        f"UPDATE messages SET {column} = ? "
                        "WHERE session_id = ?",
                        (value, "session-1"),
                    )
                with self.assertRaises(MessageIntegrityError):
                    self.repository.find_by_session("session-1")
                with self.database.connect() as connection:
                    connection.execute("DELETE FROM messages")
                self.repository.save(record)


if __name__ == "__main__":
    unittest.main()
