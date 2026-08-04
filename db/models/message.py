"""Stable-message database record."""
from dataclasses import dataclass
from datetime import datetime
from sqlite3 import Row
from typing import Optional

from pydantic import ValidationError

from db.errors import MessageIntegrityError
from .stored_message import StoredMessage


@dataclass
class Message:
    """Database record wrapping a validated StoredMessage payload."""

    session_id: str
    message_type: str
    payload_json: str
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_stored(
        cls,
        session_id: str,
        stored: StoredMessage,
    ) -> "Message":
        return cls(
            session_id=session_id,
            message_type=stored.message_type,
            payload_json=stored.model_dump_json(),
        )

    def to_stored(self) -> StoredMessage:
        try:
            stored = StoredMessage.model_validate_json(self.payload_json)
        except (ValidationError, ValueError) as error:
            raise MessageIntegrityError(
                "Stored message payload is invalid"
            ) from error

        if stored.message_type != self.message_type:
            raise MessageIntegrityError(
                "Stored message type does not match database record"
            )
        return stored

    @classmethod
    def from_row(cls, row: Row) -> "Message":
        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        message = cls(
            id=row["id"],
            session_id=row["session_id"],
            message_type=row["message_type"],
            payload_json=row["payload_json"],
            created_at=created_at,
        )
        message.to_stored()
        return message
