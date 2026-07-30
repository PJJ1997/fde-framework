"""SQLite database operations for messages."""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .models import Message


class SQLiteManager:
    """SQLite database manager for messages."""

    def __init__(self, db_path: str = "data/chat.db"):
        """Initialize SQLite manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database and create tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index on session_id for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id
            ON messages(session_id)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_contexts (
                session_id TEXT PRIMARY KEY,
                context_json TEXT NOT NULL,
                schema_version TEXT NOT NULL DEFAULT '1.0',
                context_version INTEGER NOT NULL DEFAULT 1,
                last_message_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def save_message(self, message: Message) -> int:
        """Save a message to the database.

        Args:
            message: Message object to save

        Returns:
            The ID of the saved message
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            message.session_id,
            message.role,
            message.content,
            message.created_at or datetime.now()
        ))

        message_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return message_id

    def get_messages_by_session(
        self,
        session_id: str,
        limit: Optional[int] = None,
        order_desc: bool = False,
    ) -> List[Message]:
        """Get all messages for a session.

        Args:
            session_id: Session ID to filter messages
            limit: Maximum number of messages to return
            order_desc: If True, order by created_at DESC (newest first);
                otherwise ASC (oldest first, default).

        Returns:
            List of Message objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        order = "DESC" if order_desc else "ASC"
        query = f"""
            SELECT id, session_id, role, content, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at {order}
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (session_id,))
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            messages.append(Message(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                created_at=datetime.fromisoformat(row[4]) if row[4] else None
            ))

        return messages

    def delete_messages_by_session(self, session_id: str) -> int:
        """Delete all messages for a session.

        Args:
            session_id: Session ID to delete messages

        Returns:
            Number of deleted messages
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM messages
            WHERE session_id = ?
        """, (session_id,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    def get_conversation_context(
        self,
        session_id: str,
    ) -> Optional[Dict]:
        """Get the latest structured context snapshot for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT session_id, context_json, schema_version,
                       context_version, last_message_id, updated_at
                FROM conversation_contexts
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "session_id": row[0],
            "context_json": row[1],
            "schema_version": row[2],
            "context_version": row[3],
            "last_message_id": row[4],
            "updated_at": row[5],
        }

    def save_conversation_context(
        self,
        session_id: str,
        context_json: str,
        schema_version: str,
        last_message_id: Optional[int] = None,
    ) -> int:
        """Upsert a structured context snapshot and return its version."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_contexts (
                    session_id, context_json, schema_version,
                    context_version, last_message_id, updated_at
                ) VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    context_json = excluded.context_json,
                    schema_version = excluded.schema_version,
                    context_version = conversation_contexts.context_version + 1,
                    last_message_id = COALESCE(
                        excluded.last_message_id,
                        conversation_contexts.last_message_id
                    ),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    session_id,
                    context_json,
                    schema_version,
                    last_message_id,
                ),
            )
            row = conn.execute(
                """
                SELECT context_version
                FROM conversation_contexts
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        return int(row[0])

    def delete_conversation_context(self, session_id: str) -> int:
        """Delete the structured context snapshot for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM conversation_contexts
                WHERE session_id = ?
                """,
                (session_id,),
            )
            return cursor.rowcount

    def get_all_sessions(self) -> List[str]:
        """Get all unique session IDs.

        Returns:
            List of session IDs
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT session_id
            FROM messages
            ORDER BY session_id
        """)

        sessions = [row[0] for row in cursor.fetchall()]
        conn.close()

        return sessions
