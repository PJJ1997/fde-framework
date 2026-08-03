"""Project-owned stable message storage protocol."""
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


class ProtocolModel(BaseModel):
    """Strict base for all persisted protocol values."""

    model_config = ConfigDict(extra="forbid")


class TextContent(ProtocolModel):
    type: Literal["text"] = "text"
    text: str


class ImageContent(ProtocolModel):
    type: Literal["image"] = "image"
    url: str | None = None
    data: str | None = None
    mime_type: str = Field(min_length=1)
    detail: Literal["auto", "low", "high"] = "auto"

    @model_validator(mode="after")
    def require_source(self) -> "ImageContent":
        if not self.url and not self.data:
            raise ValueError("image content requires url or data")
        return self


class FileContent(ProtocolModel):
    type: Literal["file"] = "file"
    file_id: str | None = None
    url: str | None = None
    filename: str | None = None
    mime_type: str | None = None

    @model_validator(mode="after")
    def require_reference(self) -> "FileContent":
        if not self.file_id and not self.url:
            raise ValueError("file content requires file_id or url")
        return self


class JsonContent(ProtocolModel):
    type: Literal["json"] = "json"
    data: JsonValue


ContentPart = Annotated[
    TextContent | ImageContent | FileContent | JsonContent,
    Field(discriminator="type"),
]


class StoredToolCall(ProtocolModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class StoredMessage(ProtocolModel):
    schema_version: Literal[1] = 1
    message_type: Literal["user", "assistant", "tool"]
    content: list[ContentPart] = Field(default_factory=list)
    tool_calls: list[StoredToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_message_shape(self) -> "StoredMessage":
        if self.message_type == "user":
            if self.tool_calls or self.tool_call_id is not None:
                raise ValueError(
                    "user messages cannot contain tool call fields"
                )
        elif self.message_type == "assistant":
            if self.tool_call_id is not None:
                raise ValueError(
                    "assistant messages cannot contain tool_call_id"
                )
        elif self.message_type == "tool":
            if not self.tool_call_id:
                raise ValueError("tool messages require tool_call_id")
            if self.tool_calls:
                raise ValueError(
                    "tool messages cannot contain tool_calls"
                )
        return self
