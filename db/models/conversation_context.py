"""Structured conversation context database record."""
from dataclasses import dataclass
from datetime import datetime
from sqlite3 import Row
from typing import Optional


@dataclass
class ConversationContext:
    """Latest structured context snapshot stored for a session."""

    session_id: str
    context_json: str
    context_version: int = 1
    last_message_id: Optional[int] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "context_json": self.context_json,
            "context_version": self.context_version,
            "last_message_id": self.last_message_id,
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at else None
            ),
        }

    @classmethod
    def from_row(cls, row: Row) -> "ConversationContext":
        return cls.from_dict(dict(row))

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationContext":
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return cls(
            session_id=data["session_id"],
            context_json=data["context_json"],
            context_version=data.get("context_version", 1),
            last_message_id=data.get("last_message_id"),
            updated_at=updated_at,
        )
