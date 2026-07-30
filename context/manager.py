"""Context manager for building complete agent context."""
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
)

from .models import Message
from .sqlite import SQLiteManager
from .structured import StructuredConversationContext

logger = logging.getLogger(__name__)

# LangChain message type -> class mapping
_MESSAGE_TYPES = {
    "human": HumanMessage,
    "ai": AIMessage,
    "system": SystemMessage,
    "tool": ToolMessage,
}


class ContextManager:
    """Manage and construct complete context information for agent.

    Uses LangChain message objects throughout - build() returns LangChain
    messages, and save methods accept LangChain messages.
    """

    def __init__(self, db_path: str = "data/chat.db"):
        """Initialize context manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db = SQLiteManager(db_path)

    def build(
        self,
        session_id: str,
        user_input: str,
        system_prompt: Optional[str] = None,
        include_history: bool = True,
        history_limit: Optional[int] = None
    ) -> List[BaseMessage]:
        """Build complete context for agent invocation.

        Args:
            session_id: Session ID for retrieving history messages
            system_prompt: System prompt to add at the beginning
            user_input: Current user input
            include_history: Whether to include historical messages
            history_limit: Maximum number of historical messages to include

        Returns:
            List of LangChain message objects
        """
        messages: List[BaseMessage] = []

        # Add system prompt if provided
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        # Add historical messages if requested
        if include_history:
            history_messages = self.db.get_messages_by_session(
                session_id,
                limit=history_limit
            )
            for msg in history_messages:
                # Skip system messages from history (we add fresh system prompt)
                if msg.role == "system":
                    continue
                langchain_msg = self._deserialize_message(msg.role, msg.content)
                if langchain_msg:
                    messages.append(langchain_msg)

            # Sanitize: ensure every AIMessage with tool_calls has a
            # corresponding ToolMessage so the LLM provider doesn't
            # reject the request.
            messages = self._sanitize_tool_messages(messages)

        # Add current user input (optional — workflow agents may not need it)
        if user_input:
            messages.append(HumanMessage(content=user_input))

        return messages

    def save_user_message(self, session_id: str, content: str) -> int:
        """Save user message to database.

        Args:
            session_id: Session ID
            content: Message content

        Returns:
            Message ID
        """
        return self._save_langchain_message(session_id, HumanMessage(content=content))

    def save_agent_messages(self, session_id: str, messages: List[BaseMessage]) -> List[int]:
        """Save all messages from agent execution to database.

        Args:
            session_id: Session ID
            messages: List of LangChain message objects

        Returns:
            List of saved message IDs
        """
        saved_ids = []
        for msg in messages:
            saved_id = self._save_langchain_message(session_id, msg)
            saved_ids.append(saved_id)
        return saved_ids

    def clear_session(self, session_id: str) -> int:
        """Clear all messages for a session."""
        deleted_messages = self.db.delete_messages_by_session(session_id)
        self.db.delete_conversation_context(session_id)
        return deleted_messages

    def get_structured_context(
        self,
        session_id: str,
    ) -> Optional[StructuredConversationContext]:
        """Load and validate the latest structured context snapshot."""
        stored = self.db.get_conversation_context(session_id)
        if stored is None:
            return None

        try:
            return StructuredConversationContext.model_validate_json(
                stored["context_json"]
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
        return self.db.save_conversation_context(
            session_id=session_id,
            context_json=validated.model_dump_json(),
            schema_version=validated.schema_version,
            last_message_id=last_message_id,
        )

    def get_session_history(self, session_id: str, limit: Optional[int] = None) -> List[Message]:
        """Get all messages for a session."""
        return self.db.get_messages_by_session(session_id, limit=limit)

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
        messages = self.db.get_messages_by_session(session_id, order_desc=False)
        conversations = []
        for msg in messages:
            if msg.role not in ("human", "ai"):
                continue
            text = self._extract_text_content(msg.content)
            if text is None:
                continue
            conversations.append({
                "role": "user" if msg.role == "human" else "assistant",
                "content": text,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            })
        return conversations

    @staticmethod
    def _extract_text_content(stored: str) -> Optional[str]:
        """Extract plain text content from a stored message JSON.

        Messages are stored as json.dumps(msg.model_dump()). The plain text
        lives under the "content" key. Falls back to the raw string if it
        is not valid JSON.
        """
        try:
            data = json.loads(stored)
            if isinstance(data, dict):
                return data.get("content")
            return str(data)
        except (json.JSONDecodeError, TypeError):
            return stored

    def _save_langchain_message(self, session_id: str, msg: BaseMessage) -> int:
        """Save a LangChain message to database.

        Stores the full message JSON in the content field for lossless
        reconstruction when loading history.

        Args:
            session_id: Session ID
            msg: LangChain message object

        Returns:
            Message ID
        """
        role = msg.type  # 'human', 'ai', 'system', 'tool'
        content = json.dumps(msg.model_dump(), ensure_ascii=False, default=str)

        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now()
        )
        return self.db.save_message(message)

    @staticmethod
    def _sanitize_tool_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
        """Ensure every AIMessage tool_call has a corresponding ToolMessage.

        OpenAI requires that each tool_call in an AIMessage must be followed
        by a ToolMessage with the matching tool_call_id. If a tool call
        failed without producing a ToolMessage (e.g. middleware error), or
        if a HumanMessage was incorrectly inserted between AIMessage(tool_calls)
        and ToolMessage, this method patches the gaps.

        Three passes:
        0. Deduplicate: if two AIMessages share a tool_call_id, keep only
           the one closer to its ToolMessage (removes pre-interrupt replay).
        1. Reorder: if HumanMessage appears between AIMessage(tool_calls)
           and its ToolMessages, move the HumanMessage after the ToolMessages.
        2. Add synthetic ToolMessages for missing tool_call_ids.
        """
        # --- Pass 0: deduplicate AIMessages with the same tool_call_id ---
        # When HITL interrupts, the pre-interrupt AIMessage(tool_calls) may
        # be persisted, then the resume replays the same AIMessage. We keep
        # only the last occurrence (closest to its ToolMessage).
        seen_tc_ids: Dict[str, int] = {}  # tool_call_id → index in messages
        for idx, msg in enumerate(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_id = tc.get("id")
                    if tc_id:
                        seen_tc_ids[tc_id] = idx

        # Build set of (msg_index, tc_id) pairs to REMOVE — only the
        # earlier occurrence of a duplicate tc_id is removed.
        remove_indices: Dict[int, set] = {}  # msg_index → set of tc_ids to strip
        for idx, msg in enumerate(messages):
            if not (isinstance(msg, AIMessage) and msg.tool_calls):
                continue
            ids_to_keep = []
            for tc in msg.tool_calls:
                tc_id = tc.get("id")
                if tc_id and seen_tc_ids.get(tc_id) != idx:
                    # This AIMessage is not the last one with this tc_id
                    remove_indices.setdefault(idx, set()).add(tc_id)
                else:
                    ids_to_keep.append(tc)

        deduped: List[BaseMessage] = []
        for idx, msg in enumerate(messages):
            if idx in remove_indices:
                # Remove the duplicated tool_call_ids from this AIMessage
                remaining_tc = [
                    tc for tc in msg.tool_calls
                    if tc.get("id") not in remove_indices[idx]
                ]
                if remaining_tc:
                    # Some tool_calls remain — keep the message with reduced set
                    deduped.append(AIMessage(
                        content=msg.content,
                        tool_calls=remaining_tc,
                        id=msg.id if hasattr(msg, "id") else None,
                    ))
                elif not msg.content:
                    # No tool_calls left and no text content — skip entirely
                    continue
                else:
                    # No tool_calls left but has text — keep as plain AIMessage
                    deduped.append(AIMessage(
                        content=msg.content,
                        id=msg.id if hasattr(msg, "id") else None,
                    ))
            else:
                deduped.append(msg)

        messages = deduped

        # --- Pass 1: pull ToolMessages forward to follow their AIMessage ---
        # OpenAI requires: AIMessage(tool_calls) → ToolMessage(s) → other msgs
        # When a user sends new messages while a confirmation is pending, then
        # confirms later, the ToolMessage ends up far from its AIMessage.
        # We build a global index of ToolMessages and pull them forward.
        tool_msg_by_id: Dict[str, tuple] = {}  # tool_call_id → (index, ToolMessage)
        for i, msg in enumerate(messages):
            if isinstance(msg, ToolMessage) and msg.tool_call_id:
                if msg.tool_call_id not in tool_msg_by_id:
                    tool_msg_by_id[msg.tool_call_id] = (i, msg)

        result: List[BaseMessage] = []
        pulled_indices: set = set()  # indices of ToolMessages pulled forward

        for i, msg in enumerate(messages):
            if i in pulled_indices:
                continue

            result.append(msg)

            if isinstance(msg, AIMessage) and msg.tool_calls:
                # Pull forward all ToolMessages for this AIMessage's tool_calls
                for tc in msg.tool_calls:
                    tc_id = tc.get("id")
                    if tc_id and tc_id in tool_msg_by_id:
                        idx, tm = tool_msg_by_id[tc_id]
                        if idx not in pulled_indices:
                            result.append(tm)
                            pulled_indices.add(idx)

        # --- Pass 2: add synthetic ToolMessages for missing tool_call_ids ---
        answered_ids = set()
        for msg in result:
            if isinstance(msg, ToolMessage):
                answered_ids.add(msg.tool_call_id)

        final: List[BaseMessage] = []
        for msg in result:
            final.append(msg)
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_id = tc.get("id")
                    if tc_id and tc_id not in answered_ids:
                        final.append(ToolMessage(
                            content="操作失败，请重试",
                            tool_call_id=tc_id,
                        ))
                        answered_ids.add(tc_id)

        # --- Pass 3: remove trailing AIMessage with only tool_calls ---
        # If the last message is an AIMessage with tool_calls but no text,
        # it's a dead end — no ToolMessage follows. Remove it.
        while final:
            last = final[-1]
            if isinstance(last, AIMessage) and last.tool_calls and not last.content:
                final.pop()
            else:
                break

        return final

    def _deserialize_message(self, role: str, content: str) -> Optional[BaseMessage]:
        """Deserialize a stored message back to LangChain message object.

        Args:
            role: Message type ('human', 'ai', 'system', 'tool')
            content: JSON string of the message

        Returns:
            LangChain message object, or None if deserialization fails
        """
        cls = _MESSAGE_TYPES.get(role)
        if not cls:
            return None

        try:
            data = json.loads(content)
            data.pop("type", None)  # Remove type field, not needed for construction
            return cls.model_validate(data)
        except (json.JSONDecodeError, Exception):
            # Fallback: treat content as plain text
            return cls(content=content)


# Module-level singleton instance
context_manager = ContextManager()
