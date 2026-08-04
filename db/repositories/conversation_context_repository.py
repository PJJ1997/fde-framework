"""Persistence operations for structured conversation context records."""
from contextlib import closing
from typing import Optional

from db.database import Database
from db.models import ConversationContext


class ConversationContextRepository:
    """CRUD operations for the conversation_contexts table."""

    def __init__(self, database: Database):
        self.database = database

    def get(self, session_id: str) -> Optional[ConversationContext]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                """
                SELECT session_id, context_json, context_version,
                       last_message_id, updated_at
                FROM conversation_contexts
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return ConversationContext.from_row(row) if row is not None else None

    def upsert(
        self,
        session_id: str,
        context_json: str,
        last_message_id: Optional[int] = None,
    ) -> int:
        with closing(self.database.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO conversation_contexts (
                        session_id, context_json, context_version,
                        last_message_id, updated_at
                    ) VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id) DO UPDATE SET
                        context_json = excluded.context_json,
                        context_version =
                            conversation_contexts.context_version + 1,
                        last_message_id = COALESCE(
                            excluded.last_message_id,
                            conversation_contexts.last_message_id
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        session_id,
                        context_json,
                        last_message_id,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT context_version
                    FROM conversation_contexts
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                return int(row["context_version"])

    def delete(self, session_id: str) -> int:
        with closing(self.database.connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM conversation_contexts
                    WHERE session_id = ?
                    """,
                    (session_id,),
                )
                return cursor.rowcount
