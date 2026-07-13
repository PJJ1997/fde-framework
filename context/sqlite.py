"""SQLite database operations for messages."""
import sqlite3
from pathlib import Path
from typing import List, Optional
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