"""SQLite connection infrastructure."""
import sqlite3
from contextlib import closing
from pathlib import Path

from .errors import MessageIntegrityError


_MESSAGE_COLUMNS = {
    "id",
    "session_id",
    "message_type",
    "payload_json",
    "created_at",
}


class Database:
    """Create consistently configured SQLite connections and manage schema."""

    def __init__(self, db_path: str = "data/chat.db"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Create a new database connection with consistent settings."""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize_schema(self) -> None:
        """Create the context persistence schema without changing existing data.

        Creates tables:
        - messages: User, assistant, and tool messages
        - conversation_contexts: Structured conversation contexts

        Raises:
            MessageIntegrityError: If existing messages table schema doesn't match
        """
        with closing(self.connect()) as connection:
            with connection:
                # Check if messages table exists and validate schema
                existing = connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'messages'
                    """
                ).fetchone()

                if existing is not None:
                    columns = {
                        row["name"]
                        for row in connection.execute(
                            "PRAGMA table_info(messages)"
                        )
                    }
                    if columns != _MESSAGE_COLUMNS:
                        raise MessageIntegrityError(
                            "Legacy messages schema detected; back up and "
                            "recreate the local database"
                        )

                # Create messages table
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        message_type TEXT NOT NULL CHECK (
                            message_type IN ('user', 'assistant', 'tool')
                        ),
                        payload_json TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create index for efficient session queries
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_session_id_id
                    ON messages(session_id, id)
                """)

                # Create conversation_contexts table
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_contexts (
                        session_id TEXT PRIMARY KEY,
                        context_json TEXT NOT NULL,
                        context_version INTEGER NOT NULL DEFAULT 1,
                        last_message_id INTEGER,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
