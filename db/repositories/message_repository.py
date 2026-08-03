"""Persistence operations for stable message records."""
from contextlib import closing
from typing import Optional

from db.database import Database
from db.models import Message


class MessageRepository:
    """CRUD operations for the messages table."""

    def __init__(self, database: Database):
        self.database = database

    def save(self, message: Message) -> int:
        message.to_stored()
        with closing(self.database.connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO messages (
                        session_id, message_type, payload_json,
                        schema_version, created_at
                    ) VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                    """,
                    (
                        message.session_id,
                        message.message_type,
                        message.payload_json,
                        message.schema_version,
                        message.created_at,
                    ),
                )
                return int(cursor.lastrowid)

    def find_by_session(
        self,
        session_id: str,
        limit: Optional[int] = None,
        newest_first: bool = False,
    ) -> list[Message]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be greater than or equal to zero")

        order = "DESC" if newest_first else "ASC"
        query = f"""
            SELECT id, session_id, message_type, payload_json,
                   schema_version, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id {order}
        """
        parameters: tuple = (session_id,)
        if limit is not None:
            query += " LIMIT ?"
            parameters = (session_id, limit)

        with closing(self.database.connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [Message.from_row(row) for row in rows]

    def delete_by_session(self, session_id: str) -> int:
        with closing(self.database.connect()) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM messages WHERE session_id = ?",
                    (session_id,),
                )
                return cursor.rowcount

    def list_session_ids(self) -> list[str]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT session_id
                FROM messages
                ORDER BY session_id
                """
            ).fetchall()
        return [row["session_id"] for row in rows]

    def get_last_id(self, session_id: str) -> Optional[int]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                """
                SELECT MAX(id) AS last_id
                FROM messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return row["last_id"] if row is not None else None
