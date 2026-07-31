# 数据库持久化层重构设计

## 目标

将当前 `context/sqlite.py` 中混合的 SQLite 基础设施、建表逻辑和多个业务表 CRUD 拆分为清晰的持久化层，同时保持 `ContextManager` 对 Agent、Router 暴露的业务 API 不变。

本次采用以下职责边界：

- Model 表示数据库记录和数据转换。
- Repository 负责单个聚合或表的 CRUD。
- Database 负责数据库路径、连接和事务。
- Schema 负责建表和索引。
- ContextManager 负责上下文领域编排，不了解 SQL 和表结构。

## 目录结构

在项目根目录新增 `db` 包：

```text
db/
├── __init__.py
├── database.py
├── schema.py
├── models/
│   ├── __init__.py
│   ├── message.py
│   └── conversation_context.py
└── repositories/
    ├── __init__.py
    ├── message_repository.py
    └── conversation_context_repository.py
```

完成迁移后删除：

```text
context/models.py
context/sqlite.py
```

`context/structured.py` 继续保留在 Context 领域中，因为它描述的是 Planner 使用的结构化会话语义，不是数据库记录。

## Database

`db/database.py` 提供 `Database`：

```python
class Database:
    def __init__(self, db_path: str = "data/chat.db"): ...
    def connect(self) -> sqlite3.Connection: ...
```

职责：

- 规范化数据库路径。
- 创建父目录。
- 创建带 `sqlite3.Row` 行工厂的连接。
- 启用外键约束。
- 不创建业务表。
- 不包含 Message、ConversationContext 等领域名称。

事务使用 `with database.connect() as connection:`。成功时由 SQLite context manager 提交，异常时回滚并关闭连接。

## Schema

`db/schema.py` 提供：

```python
def initialize_schema(database: Database) -> None: ...
```

它集中创建：

- `messages` 表
- `idx_messages_session_id` 索引
- `conversation_contexts` 表

第一版不引入迁移框架，也不改变现有表名和字段，确保已有 `data/chat.db` 可以继续使用。

## Models

### Message

`db/models/message.py` 保留当前 Message 字段：

- `id`
- `session_id`
- `role`
- `content`
- `created_at`

它只提供数据转换：

- `to_dict()`
- `from_row(sqlite3.Row)`
- `from_dict(dict)`

### ConversationContext

`db/models/conversation_context.py` 保留当前字段：

- `session_id`
- `context_json`
- `schema_version`
- `context_version`
- `last_message_id`
- `updated_at`

它只提供 `to_dict()`、`from_row()` 和 `from_dict()`，不执行 SQL。

## Repositories

### MessageRepository

接口：

```python
class MessageRepository:
    def __init__(self, database: Database): ...
    def save(self, message: Message) -> int: ...
    def find_by_session(
        self,
        session_id: str,
        limit: Optional[int] = None,
        newest_first: bool = False,
    ) -> list[Message]: ...
    def delete_by_session(self, session_id: str) -> int: ...
    def list_session_ids(self) -> list[str]: ...
```

所有排序方向由固定布尔参数决定，不允许调用方传入原始 SQL。`limit` 使用绑定参数并拒绝负数。

### ConversationContextRepository

接口：

```python
class ConversationContextRepository:
    def __init__(self, database: Database): ...
    def get(self, session_id: str) -> Optional[ConversationContext]: ...
    def upsert(
        self,
        session_id: str,
        context_json: str,
        schema_version: str,
        last_message_id: Optional[int] = None,
    ) -> int: ...
    def delete(self, session_id: str) -> int: ...
```

`upsert` 继续维持当前版本自增和 `last_message_id` 的 `COALESCE` 行为。

## ContextManager

`ContextManager` 构造时完成依赖组装：

1. 创建 `Database`。
2. 调用 `initialize_schema`。
3. 创建 `MessageRepository`。
4. 创建 `ConversationContextRepository`。

Manager 中的调用调整为：

- 历史消息：`message_repository.find_by_session`
- 保存消息：`message_repository.save`
- 清理会话：分别调用两个 Repository
- 结构化上下文：`conversation_context_repository.get/upsert/delete`

以下公开方法签名和行为保持不变：

- `build`
- `save_user_message`
- `save_agent_messages`
- `clear_session`
- `get_structured_context`
- `save_structured_context`
- `record_tool_facts`
- `get_session_history`
- `get_conversations`

模块级 `context_manager = ContextManager()` 第一版保留，以避免修改所有 Agent 和 Router。Repository 作为明确属性暴露，移除含义不清的 `manager.db` 属性。

## 公共导入兼容

`context/__init__.py` 继续导出：

- `ContextManager`
- `context_manager`
- `Message`
- `ConversationContext`
- 结构化上下文模型

`Message` 和 `ConversationContext` 改为从 `db.models` 重导出。

删除 `SQLiteManager` 公共导出。当前仓库没有 `ContextManager` 之外的生产代码依赖它；如果外部调用者直接使用过 `context.SQLiteManager`，这是一个需要同步迁移的破坏性变更。

## 错误和事务

- Repository 不吞掉 `sqlite3` 异常。
- 单次 Repository 写操作在自身连接事务中完成。
- `clear_session` 当前由两次独立删除组成，保持现有行为；跨表原子事务留到确有业务要求时再增加 Unit of Work，避免第一版过度设计。
- 数据反序列化失败仍由 `ContextManager.get_structured_context` 捕获并记录 warning。

## 测试策略

采用测试驱动迁移：

1. Database 测试验证父目录创建、Row factory 和连接隔离。
2. Schema 测试验证两个表和索引存在。
3. MessageRepository 测试覆盖保存、顺序、limit、删除和 session 列表。
4. ConversationContextRepository 测试覆盖 upsert、版本递增、`last_message_id` 保留和删除。
5. ContextManager 测试改为通过 Repository 公开接口检查行为，不再访问 `manager.db`。
6. 运行完整测试套件，确保 Agent、Router 和结构化 Context 行为无回归。

## 非目标

- 不引入 SQLAlchemy、Alembic 或其他 ORM。
- 不迁移 LangGraph checkpoint 数据库。
- 不迁移 ERP、RAG 等其他子系统的 SQLite 实现。
- 不改变现有 SQLite 表结构和已有数据。
- 不在本次拆分 `ContextManager` 中的 LangChain 消息清洗算法。
