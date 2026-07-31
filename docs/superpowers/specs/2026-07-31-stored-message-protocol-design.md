# 自定义消息存储协议设计

## 目标

建立由项目自身维护的稳定消息存储协议，使数据库格式不依赖 LangChain 的 Pydantic Model、序列化结构或版本变化。

设计目标：

- 支持文本、图片、文件和 JSON 多模态内容。
- 支持 Assistant Tool Call 和 Tool Result。
- 不持久化 System Prompt。
- 不兼容当前 `messages` 表里的旧 LangChain `model_dump()` 数据。
- LangChain 仅存在于 Adapter 边界。
- 数据库按照自定义协议存储和校验消息。

## 架构

```text
LangChain BaseMessage
          │
          ▼
LangChainMessageAdapter
          │
          ▼
StoredMessage
          │
          ▼
MessageRepository
          │
          ▼
SQLite messages
```

反向读取使用相同边界：

```text
SQLite messages
      │
      ▼
StoredMessage
      │
      ▼
LangChainMessageAdapter
      │
      ▼
当前版本 LangChain BaseMessage
```

数据库、Model 和 Repository 不 import LangChain。Adapter 是持久化子系统中唯一允许依赖 `langchain_core.messages` 的组件。

## 文件结构

```text
context/
├── manager.py
├── adapters/
│   ├── __init__.py
│   └── langchain_message_adapter.py
└── structured.py

db/
├── models/
│   ├── message.py
│   └── stored_message.py
└── repositories/
    └── message_repository.py
```

`StoredMessage` 和 Content Part 属于稳定存储协议，因此放在 `db/models/stored_message.py`。LangChain 转换放在 `context/adapters`。

## JSON 类型

协议只允许标准 JSON 值：

```python
JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
```

不使用 `default=str`。无法表示为标准 JSON 的数据必须在 Adapter 边界被明确拒绝或转换为已定义的稳定字段。

## Content Part

所有消息的 `content` 始终是 Content Part 数组。纯文本消息同样使用数组，避免调用方处理 `str | list` 两种形态。

### TextContent

```python
class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str
```

### ImageContent

```python
class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    url: str | None = None
    data: str | None = None
    mime_type: str
    detail: Literal["auto", "low", "high"] = "auto"
```

校验规则：

- `url` 和 `data` 至少存在一个。
- 第一版允许二者同时存在，Adapter 优先使用 URL。
- `data` 保存 Base64 内容但不包含 `data:` 前缀；`mime_type` 单独保存。
- 本协议不负责文件上传、对象存储或 URL 生命周期。

### FileContent

```python
class FileContent(BaseModel):
    type: Literal["file"] = "file"
    file_id: str | None = None
    url: str | None = None
    filename: str | None = None
    mime_type: str | None = None
```

校验规则：

- `file_id` 和 `url` 至少存在一个。
- 第一版不把任意文件二进制直接写入消息表。

### JsonContent

```python
class JsonContent(BaseModel):
    type: Literal["json"] = "json"
    data: JSONValue
```

Tool Result 是 JSON 时优先使用 `JsonContent`，避免把结构化结果提前字符串化。

### 联合类型

```python
ContentPart = Annotated[
    TextContent | ImageContent | FileContent | JsonContent,
    Field(discriminator="type"),
]
```

## Tool Call

```python
class StoredToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, JSONValue]
```

规则：

- `id`、`name` 不允许为空字符串。
- `arguments` 必须是 JSON Object。
- Provider 或 LangChain 专属 Tool Call 字段不进入稳定协议。

## StoredMessage

```python
class StoredMessage(BaseModel):
    schema_version: Literal[1] = 1
    message_type: Literal["user", "assistant", "tool"]
    content: list[ContentPart] = Field(default_factory=list)
    tool_calls: list[StoredToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    metadata: dict[str, JSONValue] = Field(default_factory=dict)
```

跨字段校验：

- `user` 不允许包含 `tool_calls` 或 `tool_call_id`。
- `assistant` 允许文本、多模态内容和 `tool_calls`，不允许 `tool_call_id`。
- `tool` 必须包含非空 `tool_call_id`，不允许包含 `tool_calls`。
- `system` 不属于协议允许值，因此无法写入数据库。
- 消息允许空 `content` 的唯一常见情况是 Assistant 仅产生 Tool Call。

## Metadata

允许的 Metadata 是由项目维护的稳定业务信息，例如：

- `agent_name`
- `workflow_name`
- `trace_id`
- `source`

第一版不建立 Metadata Key 白名单，但值必须满足 `JSONValue`。

禁止写入：

- API key 或认证信息
- System Prompt
- LangChain 内部序列化字段
- Azure/OpenAI HTTP header
- Provider 原始响应对象
- 完整 response metadata
- token usage 和延迟统计

Token 和调用性能以后进入独立的 LLM 调用审计表。

## 数据库表

由于不需要兼容旧消息，初始化时重建开发数据库中的 `messages` 表。本次只修改 schema 定义；现有本地 `data/chat.db` 由开发者删除后重新初始化，不在应用启动时静默删除生产数据。

新表：

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_type TEXT NOT NULL
        CHECK (message_type IN ('user', 'assistant', 'tool')),
    payload_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_session_id_id
ON messages(session_id, id);
```

字段说明：

- `message_type` 用于过滤和完整性校验。
- `payload_json` 是 `StoredMessage.model_dump_json()`。
- `schema_version` 与 Payload 内版本有意重复，用于快速判断和约束。
- 消息顺序使用自增 `id`，不依赖 `created_at`。

Repository 读取时必须验证：

- 数据库 `message_type` 等于 Payload `message_type`。
- 数据库 `schema_version` 等于 Payload `schema_version`。
- Payload 可以通过当前 `StoredMessage` 校验。

不一致时抛出明确的数据完整性异常，不静默修复。

## Message 数据库 Model

```python
@dataclass
class Message:
    session_id: str
    message_type: str
    payload_json: str
    schema_version: int = 1
    id: int | None = None
    created_at: datetime | None = None
```

该 Model 表示数据库记录，不等同于 `StoredMessage`：

- `Message` 是表记录。
- `StoredMessage` 是 Payload 协议。
- Repository 负责二者之间的完整性校验。

## LangChain Adapter

公开接口：

```python
class LangChainMessageAdapter:
    def to_stored(self, message: BaseMessage) -> StoredMessage: ...
    def to_langchain(self, message: StoredMessage) -> BaseMessage: ...
```

### HumanMessage

- 映射为 `message_type="user"`。
- 字符串 content 映射为一个 `TextContent`。
- LangChain 多模态数组映射到协议 Content Part。
- 不保存 System Prompt、response metadata 或 LangChain ID。

### AIMessage

- 映射为 `message_type="assistant"`。
- content 映射为 Content Part 数组。
- `tool_calls` 映射为 `StoredToolCall`。
- 不保存 `invalid_tool_calls`；存在 invalid tool call 时明确拒绝持久化，避免不可执行数据进入历史。

### ToolMessage

- 映射为 `message_type="tool"`。
- `tool_call_id` 必须存在。
- Dict/List 结果映射为 `JsonContent`。
- 字符串结果映射为 `TextContent`。
- `name` 在可用时保留。

### SystemMessage

`to_stored` 明确抛出 `UnsupportedStoredMessageError`。ContextManager 在保存 Agent Message 时跳过 SystemMessage，使 System Prompt 只由代码配置维护。

### 未支持类型

ChatMessage、FunctionMessage 或未来未知 Message 类型第一版明确拒绝，不做猜测性映射。

## ContextManager 调整

`ContextManager` 组合：

- `MessageRepository`
- `ConversationContextRepository`
- `LangChainMessageAdapter`

保存流程：

```text
BaseMessage
→ 跳过 SystemMessage
→ Adapter.to_stored
→ StoredMessage.model_dump_json
→ Message
→ MessageRepository.save
```

读取流程：

```text
MessageRepository.find_by_session
→ StoredMessage.model_validate_json
→ Adapter.to_langchain
→ ToolMessage Sanitizer
→ Agent
```

`get_conversations` 从 `StoredMessage.content` 中提取文本 Content Part，不再解析 LangChain `model_dump()`。

`get_session_history` 的返回类型调整为 `list[StoredMessage]`，使 Planner Context Builder 不依赖数据库记录格式。需要数据库 ID 时后续增加独立查询接口。

## 错误类型

新增：

```python
class StoredMessageError(ValueError): ...
class UnsupportedStoredMessageError(StoredMessageError): ...
class MessageIntegrityError(StoredMessageError): ...
```

- 协议字段不合法：Pydantic ValidationError。
- LangChain 类型或 Content Part 不支持：`UnsupportedStoredMessageError`。
- 数据库列与 Payload 不一致：`MessageIntegrityError`。
- 不捕获并字符串化错误。

## 测试矩阵

### StoredMessage

- 纯文本 User。
- 文本 Assistant。
- URL 图片。
- Base64 图片。
- 缺少图片来源被拒绝。
- File ID 文件。
- URL 文件。
- 缺少文件引用被拒绝。
- JSON Content。
- Assistant Tool Call。
- Tool Message 缺少 Tool Call ID 被拒绝。
- User 携带 Tool Call 被拒绝。
- System 类型被拒绝。

### Adapter

- HumanMessage 文本双向转换。
- HumanMessage 多模态双向转换。
- AIMessage 文本双向转换。
- AIMessage Tool Calls 双向转换。
- ToolMessage 文本结果双向转换。
- ToolMessage JSON 结果双向转换。
- SystemMessage 不持久化。
- 未知 Content Part 被拒绝。
- invalid tool calls 被拒绝。

### Repository

- 保存并恢复 Payload。
- 按自增 ID 排序。
- message type 不一致被拒绝。
- schema version 不一致被拒绝。
- 非法 JSON 被拒绝。
- session 删除和 limit 行为保持不变。

### ContextManager

- 保存 User/Assistant/Tool 消息。
- SystemMessage 被跳过。
- 构建 LangChain 历史。
- Planner 获取 `StoredMessage` 历史。
- `get_conversations` 只输出 User/Assistant 文本部分。
- ToolMessage Sanitizer 行为保持不变。

## 数据清理和启动要求

由于明确不兼容旧表结构，实施后开发者需要删除本地旧数据库：

```bash
rm data/chat.db
```

应用不会自动删除已有数据库。若旧表仍存在，Schema 校验应在启动时检测字段不匹配并给出明确错误，提示开发者删除或迁移数据库。

此操作只针对本地开发数据库。生产环境上线前必须使用显式迁移流程，不能依赖删除文件。

## 非目标

- 不支持旧 LangChain `model_dump()` 消息读取。
- 不保存 System Prompt。
- 不保存任意 Python 对象。
- 不建立 Tool Call 独立关系表。
- 不建立文件对象存储。
- 不建立 token usage 或 LLM tracing 表。
- 不在本次拆分 ToolMessage Sanitizer；只保持其行为。
