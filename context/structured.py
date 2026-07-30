"""Structured working memory for a conversation."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CurrentRequest(BaseModel):
    """Normalized representation of the current user turn."""

    raw_text: str = ""
    intent: str = ""
    is_follow_up: bool = False


class ResolvedReference(BaseModel):
    """Resolution status for a referring expression."""

    expression: str
    entity_type: str
    resolved_id: Optional[str] = None
    status: Literal["resolved", "ambiguous", "unresolved"]


class ToolFact(BaseModel):
    """Compact trusted fact produced by a successful tool execution."""

    tool: str
    status: Literal["success"] = "success"
    data: Dict[str, Any] = Field(default_factory=dict)


class StructuredConversationContext(BaseModel):
    """Latest structured context snapshot for a conversation session."""

    schema_version: str = "1.0"
    current_request: CurrentRequest = Field(default_factory=CurrentRequest)
    entities: Dict[str, Dict[str, Dict[str, Any]]] = Field(default_factory=dict)
    active_entities: Dict[str, str] = Field(default_factory=dict)
    references: List[ResolvedReference] = Field(default_factory=list)
    constraints: List[Dict[str, Any]] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    ambiguities: List[Dict[str, Any]] = Field(default_factory=list)
    tool_facts: List[ToolFact] = Field(default_factory=list)
    summary: str = ""

    @classmethod
    def empty(cls) -> "StructuredConversationContext":
        """Create an empty context with stable schema defaults."""
        return cls()
