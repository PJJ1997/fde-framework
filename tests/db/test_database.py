import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.database import Database
from db.errors import MessageIntegrityError
# Schema is now part of Database class


class DatabaseTests(unittest.TestCase):
    def test_connection_configures_directory_rows_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "nested" / "chat.db"
            database = Database(str(db_path))

            self.assertTrue(db_path.parent.is_dir())
            with database.connect() as connection:
                self.assertIs(connection.row_factory, sqlite3.Row)
                enabled = connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]

            self.assertEqual(enabled, 1)

    def test_initialize_schema_creates_tables_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "chat.db"))

            database.initialize_schema()

            with database.connect() as connection:
                objects = {
                    (row["type"], row["name"])
                    for row in connection.execute(
                        """
                        SELECT type, name
                        FROM sqlite_master
                        WHERE name IN (
                            'messages',
                            'conversation_contexts',
                            'idx_messages_session_id_id'
                        )
                        """
                    )
                }

            self.assertEqual(objects, {
                ("table", "messages"),
                ("table", "conversation_contexts"),
                ("index", "idx_messages_session_id_id"),
            })

    def test_initialize_schema_rejects_legacy_messages_table(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "chat.db"))
            with database.connect() as connection:
                connection.execute("""
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL
                    )
                """)

            with self.assertRaises(MessageIntegrityError):
                database.initialize_schema()


if __name__ == "__main__":
    unittest.main()
