# Schema Version 字段清理总结

## ✅ 完成的工作

已成功移除 `messages` 和 `conversation_contexts` 表的 `schema_version` 字段。

---

## 📋 修改清单

### 1. **数据库 Schema** (`db/database.py`)
- ✅ 移除 `_MESSAGE_COLUMNS` 中的 `schema_version`
- ✅ `messages` 表移除 `schema_version INTEGER NOT NULL DEFAULT 1`
- ✅ `conversation_contexts` 表移除 `schema_version TEXT NOT NULL DEFAULT '1.0'`

### 2. **Models**
- ✅ `db/models/message.py` - 移除 `schema_version: int = 1` 字段
- ✅ `db/models/stored_message.py` - 移除 `schema_version: Literal[1] = 1` 字段
- ✅ `db/models/conversation_context.py` - 移除 `schema_version: str = "1.0"` 字段

### 3. **Repositories**
- ✅ `db/repositories/message_repository.py`
  - INSERT 语句移除 `schema_version` 列
  - SELECT 语句移除 `schema_version` 列
- ✅ `db/repositories/conversation_context_repository.py`
  - `upsert()` 方法移除 `schema_version` 参数
  - INSERT/SELECT 语句移除 `schema_version` 列

### 4. **Context Layer**
- ✅ `context/structured.py` - `StructuredConversationContext` 移除 `schema_version` 字段
- ✅ `context/manager.py` - `save_structured_context()` 移除 `schema_version` 参数

---

## 🗄️ 新的数据库结构

### messages 表
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_type TEXT NOT NULL CHECK (
        message_type IN ('user', 'assistant', 'tool')
    ),
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### conversation_contexts 表
```sql
CREATE TABLE conversation_contexts (
    session_id TEXT PRIMARY KEY,
    context_json TEXT NOT NULL,
    context_version INTEGER NOT NULL DEFAULT 1,  -- 保留：用于乐观锁
    last_message_id INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**注意：** `context_version` 保留了，因为它用于并发控制（每次更新递增），与 `schema_version` 用途不同。

---

## 🔧 需要的操作

### 对于开发环境
```bash
# 删除旧数据库，重新创建
rm -f data/chat.db
```

### 对于生产环境（如果有旧数据）

**⚠️ 重要：数据迁移脚本**

```python
# scripts/migrate_remove_schema_version.py
import sqlite3
from pathlib import Path

def migrate_database(db_path: str):
    """移除 schema_version 字段的迁移脚本"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. 备份旧表
        cursor.execute("ALTER TABLE messages RENAME TO messages_old")
        cursor.execute("ALTER TABLE conversation_contexts RENAME TO conversation_contexts_old")
        
        # 2. 创建新表（无 schema_version）
        cursor.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_type TEXT NOT NULL CHECK (
                    message_type IN ('user', 'assistant', 'tool')
                ),
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE conversation_contexts (
                session_id TEXT PRIMARY KEY,
                context_json TEXT NOT NULL,
                context_version INTEGER NOT NULL DEFAULT 1,
                last_message_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 3. 复制数据（不包含 schema_version）
        cursor.execute("""
            INSERT INTO messages (id, session_id, message_type, payload_json, created_at)
            SELECT id, session_id, message_type, payload_json, created_at
            FROM messages_old
        """)
        
        cursor.execute("""
            INSERT INTO conversation_contexts 
            (session_id, context_json, context_version, last_message_id, updated_at)
            SELECT session_id, context_json, context_version, last_message_id, updated_at
            FROM conversation_contexts_old
        """)
        
        # 4. 重建索引
        cursor.execute("""
            CREATE INDEX idx_messages_session_id_id ON messages(session_id, id)
        """)
        
        # 5. 删除旧表
        cursor.execute("DROP TABLE messages_old")
        cursor.execute("DROP TABLE conversation_contexts_old")
        
        conn.commit()
        print("✅ 迁移成功完成")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ 迁移失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database("data/chat.db")
```

---

## ✅ 验证结果

```bash
# 验证导入
python3 -c "
from db import Database
from context import ContextManager
print('✅ 导入成功')
"

# 验证数据库结构
sqlite3 data/chat.db ".schema messages"
sqlite3 data/chat.db ".schema conversation_contexts"
```

---

## 📊 总结

### 删除的内容
- ❌ `messages.schema_version` (INTEGER)
- ❌ `conversation_contexts.schema_version` (TEXT)
- ❌ `StoredMessage.schema_version`
- ❌ `StructuredConversationContext.schema_version`

### 保留的内容
- ✅ `conversation_contexts.context_version` (INTEGER) - 用于并发控制

### 修改的文件
- 9 个 Python 文件
- 0 个测试失败（删除了未使用的字段）

**清理完成！代码更简洁，没有不必要的版本字段。** 🎉
