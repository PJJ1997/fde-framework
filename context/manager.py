"""Context manager for building complete agent context."""
import logging
from typing import Any, List, Optional

from context.adapters import LangChainMessageAdapter
from context.adapters.base import MessageAdapter
from db import Database
from db.models import Message, StoredMessage, TextContent
from db.repositories import (
    ConversationContextRepository,
    MessageRepository,
)
from .structured import StructuredConversationContext, ToolFact

logger = logging.getLogger(__name__)

class ContextManager:
    """Manage and construct complete context information for agent.

    Uses MessageAdapter interface to remain framework-agnostic.
    The adapter handles conversion between framework-specific messages
    (e.g., LangChain) and the storage layer.
    """

    def __init__(
        self,
        db_path: str = "data/chat.db",
        message_adapter: Optional[MessageAdapter] = None
    ):
        """Initialize context manager.

        Args:
            db_path: Path to the SQLite database file
            message_adapter: Message adapter for framework-specific conversion.
                           Defaults to LangChainMessageAdapter if not provided.
        """
        database = Database(db_path)
        database.initialize_schema()
        self.message_repository = MessageRepository(database)
        self.conversation_context_repository = (
            ConversationContextRepository(database)
        )
        self.message_adapter = message_adapter or LangChainMessageAdapter()

    def build(
        self,
        session_id: str,
        user_input: str,
        system_prompt: Optional[str] = None,
        include_history: bool = True,
        history_limit: Optional[int] = None
    ) -> List[Any]:
        """Build complete context for agent invocation.

        Args:
            session_id: Session ID for retrieving history messages
            system_prompt: System prompt to add at the beginning
            user_input: Current user input
            include_history: Whether to include historical messages
            history_limit: Maximum number of historical messages to include

        Returns:
            List of framework-specific message objects (type depends on adapter)
        """
        messages: List[Any] = []

        # Add system prompt if provided
        if system_prompt:
            messages.append(self.message_adapter.create_system_message(system_prompt))

        # Add historical messages if requested
        if include_history:
            history_messages = self.message_repository.find_by_session(
                session_id,
                limit=history_limit
            )
            messages.extend(
                self.message_adapter.to_framework(record.to_stored())
                for record in history_messages
            )

            # Sanitize: ensure message validity (e.g., AIMessage/ToolMessage pairing)
            messages = self.message_adapter.sanitize_messages(messages)

        # Add current user input (optional — workflow agents may not need it)
        if user_input:
            messages.append(self.message_adapter.create_user_message(user_input))

        return messages

    def save_user_message(self, session_id: str, content: str) -> int:
        """Save user message to database.

        Args:
            session_id: Session ID
            content: Message content

        Returns:
            Message ID
        """
        user_message = self.message_adapter.create_user_message(content)
        return self._save_framework_message(session_id, user_message)

    def save_agent_messages(self, session_id: str, messages: List[Any]) -> List[int]:
        """Save all messages from agent execution to database.

        Args:
            session_id: Session ID
            messages: List of framework-specific messages from agent execution

        Returns:
            List of saved message IDs
        """
        saved_ids = []
        for message in messages:
            # Skip system messages (they are not persisted)
            if self.message_adapter.get_message_type(message) == "system":
                continue
            saved_ids.append(
                self._save_framework_message(session_id, message)
            )
        return saved_ids

    def clear_session(self, session_id: str) -> int:
        """Clear all messages for a session."""
        deleted_messages = self.message_repository.delete_by_session(
            session_id
        )
        self.conversation_context_repository.delete(session_id)
        return deleted_messages

    def get_structured_context(
        self,
        session_id: str,
    ) -> Optional[StructuredConversationContext]:
        """Load and validate the latest structured context snapshot."""
        stored = self.conversation_context_repository.get(session_id)
        if stored is None:
            return None

        try:
            return StructuredConversationContext.model_validate_json(
                stored.context_json
            )
        except Exception as error:
            logger.warning(
                "Invalid structured context for session %s: %s",
                session_id,
                error,
            )
            return None

    def save_structured_context(
        self,
        session_id: str,
        context: StructuredConversationContext,
        last_message_id: Optional[int] = None,
    ) -> int:
        """Validate and persist a complete structured context snapshot."""
        validated = StructuredConversationContext.model_validate(context)
        return self.conversation_context_repository.upsert(
            session_id=session_id,
            context_json=validated.model_dump_json(),
            schema_version=validated.schema_version,
            last_message_id=last_message_id,
        )

    def record_tool_facts(
        self,
        session_id: str,
        step_results: list,
    ) -> Optional[StructuredConversationContext]:
        """Persist compact facts from successful tool executions."""
        context = self.get_structured_context(session_id)
        if context is None:
            return None

        new_facts = [
            ToolFact(
                tool=step.tool_name,
                data=step.result,
            )
            for step in step_results
            if step.success
        ]
        if not new_facts:
            return context

        updated = context.model_copy(
            update={
                "tool_facts": [
                    *context.tool_facts,
                    *new_facts,
                ][-20:]
            }
        )
        self.save_structured_context(session_id, updated)
        return updated

    def get_session_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[StoredMessage]:
        """Get stable stored messages for a session."""
        return [
            record.to_stored()
            for record in self.message_repository.find_by_session(
                session_id,
                limit=limit,
            )
        ]

    def get_last_message_id(self, session_id: str) -> Optional[int]:
        """Return the latest persisted message identifier."""
        return self.message_repository.get_last_id(session_id)

    def get_conversations(self, session_id: str) -> List[dict]:
        """Return user/assistant messages for a session, newest first.

        Filters out system and tool messages. Extracts plain text content
        from the stored message JSON so no internal metadata (tool_calls,
        additional_kwargs, etc.) is exposed.

        Args:
            session_id: Session ID to query.

        Returns:
            List of dicts: {"role": "user"|"assistant", "content": str,
            "created_at": iso-string}, ordered newest-first.
        """
        records = self.message_repository.find_by_session(session_id)
        conversations = []
        for record in records:
            message = record.to_stored()
            if message.message_type not in ("user", "assistant"):
                continue
            text = "".join(
                part.text
                for part in message.content
                if isinstance(part, TextContent)
            )
            if not text:
                continue
            conversations.append({
                "role": message.message_type,
                "content": text,
                "created_at": (
                    record.created_at.isoformat()
                    if record.created_at else None
                ),
            })
        return conversations

    def _save_framework_message(self, session_id: str, msg: Any) -> int:
        """Save a framework-specific message to database.

        Converts the message via the adapter and stores it for lossless
        reconstruction when loading history.

        Args:
            session_id: Session ID
            msg: Framework-specific message object (type depends on adapter)

        Returns:
            Message ID
        """
        stored = self.message_adapter.from_framework(msg)
        message = Message.from_stored(
            session_id=session_id,
            stored=stored,
        )
        return self.message_repository.save(message)

# Module-level singleton instance
context_manager = ContextManager()
