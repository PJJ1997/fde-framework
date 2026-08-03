"""Translate between LangChain messages and the stable stored protocol."""
import mimetypes
from typing import Dict, List

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from db.errors import UnsupportedStoredMessageError
from db.models import (
    FileContent,
    ImageContent,
    JsonContent,
    StoredMessage,
    StoredToolCall,
    TextContent,
)
from .base import MessageAdapter


class LangChainMessageAdapter(MessageAdapter):
    """LangChain-specific implementation of MessageAdapter.

    Translates between LangChain messages and the stable stored protocol.
    """

    def from_framework(self, message: BaseMessage) -> StoredMessage:
        """Convert LangChain BaseMessage to StoredMessage.

        Args:
            message: LangChain BaseMessage

        Returns:
            StoredMessage for database storage
        """
        return self.to_stored(message)

    def to_framework(self, stored: StoredMessage) -> BaseMessage:
        """Convert StoredMessage to LangChain BaseMessage.

        Args:
            stored: StoredMessage from database

        Returns:
            LangChain BaseMessage
        """
        return self.to_langchain(stored)

    def create_system_message(self, content: str) -> SystemMessage:
        """Create a LangChain SystemMessage.

        Args:
            content: System message content

        Returns:
            LangChain SystemMessage
        """
        return SystemMessage(content=content)

    def create_user_message(self, content: str) -> HumanMessage:
        """Create a LangChain HumanMessage.

        Args:
            content: User message content

        Returns:
            LangChain HumanMessage
        """
        return HumanMessage(content=content)

    def sanitize_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Sanitize LangChain messages to ensure validity.

        Ensures every AIMessage with tool_calls has corresponding ToolMessage.

        Args:
            messages: List of LangChain messages

        Returns:
            Sanitized list of messages
        """
        return self._sanitize_tool_messages(messages)

    def get_message_type(self, message: BaseMessage) -> str:
        """Get the type of a LangChain message.

        Args:
            message: LangChain BaseMessage

        Returns:
            Message type string
        """
        if isinstance(message, HumanMessage):
            return "user"
        elif isinstance(message, AIMessage):
            return "assistant"
        elif isinstance(message, ToolMessage):
            return "tool"
        elif isinstance(message, SystemMessage):
            return "system"
        else:
            return "unknown"

    # ========== Original methods (legacy compatibility) ==========

    def to_stored(self, message: BaseMessage) -> StoredMessage:
        if isinstance(message, SystemMessage):
            raise UnsupportedStoredMessageError(
                "SystemMessage is not persisted"
            )

        content = self._content_to_stored(message.content)
        name = getattr(message, "name", None)

        if isinstance(message, HumanMessage):
            return StoredMessage(
                message_type="user",
                content=content,
                name=name,
            )

        if isinstance(message, AIMessage):
            if message.invalid_tool_calls:
                raise UnsupportedStoredMessageError(
                    "AIMessage contains invalid tool calls"
                )
            tool_calls = [
                StoredToolCall(
                    id=tool_call["id"],
                    name=tool_call["name"],
                    arguments=tool_call.get("args", {}),
                )
                for tool_call in message.tool_calls
            ]
            return StoredMessage(
                message_type="assistant",
                content=content,
                tool_calls=tool_calls,
                name=name,
            )

        if isinstance(message, ToolMessage):
            return StoredMessage(
                message_type="tool",
                content=content,
                tool_call_id=message.tool_call_id,
                name=name,
            )

        raise UnsupportedStoredMessageError(
            f"Unsupported LangChain message: {type(message).__name__}"
        )

    def to_langchain(self, message: StoredMessage) -> BaseMessage:
        content = self._content_to_langchain(message)

        if message.message_type == "user":
            return HumanMessage(content=content, name=message.name)
        if message.message_type == "assistant":
            return AIMessage(
                content=content,
                name=message.name,
                tool_calls=[
                    {
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "args": tool_call.arguments,
                        "type": "tool_call",
                    }
                    for tool_call in message.tool_calls
                ],
            )
        return ToolMessage(
            content=content,
            tool_call_id=message.tool_call_id or "",
            name=message.name,
        )

    def _content_to_stored(self, content) -> list:
        if isinstance(content, str):
            return [TextContent(text=content)] if content else []
        if not isinstance(content, list):
            raise UnsupportedStoredMessageError(
                f"Unsupported message content: {type(content).__name__}"
            )

        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(TextContent(text=block))
                continue
            if not isinstance(block, dict):
                raise UnsupportedStoredMessageError(
                    "Content blocks must be strings or objects"
                )

            block_type = block.get("type")
            if block_type == "text":
                parts.append(TextContent(text=block.get("text", "")))
            elif block_type == "image_url":
                parts.append(self._image_url_to_stored(block))
            elif block_type == "image":
                parts.append(ImageContent(
                    url=block.get("url"),
                    data=block.get("data"),
                    mime_type=block.get("mime_type", "image/*"),
                    detail=block.get("detail", "auto"),
                ))
            elif block_type == "file":
                file_data = block.get("file", block)
                parts.append(FileContent(
                    file_id=file_data.get("file_id"),
                    url=file_data.get("url"),
                    filename=file_data.get("filename"),
                    mime_type=file_data.get("mime_type"),
                ))
            elif block_type == "json":
                parts.append(JsonContent(data=block.get("data")))
            else:
                raise UnsupportedStoredMessageError(
                    f"Unsupported content block: {block_type}"
                )
        return parts

    def _image_url_to_stored(self, block: dict) -> ImageContent:
        image_url = block.get("image_url")
        if isinstance(image_url, str):
            url = image_url
            detail = "auto"
        elif isinstance(image_url, dict):
            url = image_url.get("url")
            detail = image_url.get("detail", "auto")
        else:
            raise UnsupportedStoredMessageError(
                "image_url block requires a URL"
            )

        if url and url.startswith("data:"):
            header, separator, data = url.partition(",")
            if not separator or ";base64" not in header:
                raise UnsupportedStoredMessageError(
                    "Only base64 data image URLs are supported"
                )
            mime_type = header[5:].split(";", 1)[0]
            return ImageContent(
                data=data,
                mime_type=mime_type,
                detail=detail,
            )

        mime_type = mimetypes.guess_type(url or "")[0] or "image/*"
        return ImageContent(
            url=url,
            mime_type=mime_type,
            detail=detail,
        )

    def _content_to_langchain(self, message: StoredMessage):
        if len(message.content) == 1:
            only = message.content[0]
            if isinstance(only, TextContent):
                return only.text

        blocks = []
        for part in message.content:
            if isinstance(part, TextContent):
                blocks.append({"type": "text", "text": part.text})
            elif isinstance(part, ImageContent):
                url = part.url or (
                    f"data:{part.mime_type};base64,{part.data}"
                )
                blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": url,
                        "detail": part.detail,
                    },
                })
            elif isinstance(part, FileContent):
                blocks.append({
                    "type": "file",
                    "file": {
                        key: value
                        for key, value in {
                            "file_id": part.file_id,
                            "url": part.url,
                            "filename": part.filename,
                            "mime_type": part.mime_type,
                        }.items()
                        if value is not None
                    },
                })
            elif isinstance(part, JsonContent):
                blocks.append({
                    "type": "json",
                    "data": part.data,
                })
        return blocks

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
