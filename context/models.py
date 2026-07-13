"""Message data models."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    """Message data structure."""

    session_id: str
    role: str  # "system", "user", "assistant", "tool"
    content: str
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert Message to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Create Message from dictionary."""
        created_at = None
        if data.get("created_at"):
            if isinstance(data["created_at"], str):
                created_at = datetime.fromisoformat(data["created_at"])
            elif isinstance(data["created_at"], datetime):
                created_at = data["created_at"]

        return cls(
            id=data.get("id"),
            session_id=data["session_id"],
            role=data["role"],
            content=data["content"],
            created_at=created_at
        )