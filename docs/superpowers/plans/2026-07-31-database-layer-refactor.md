# Database Persistence Layer Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mixed `context.sqlite` persistence class with a root `db` package containing infrastructure, schema, pure models, and table-specific repositories while preserving `ContextManager` behavior.

**Architecture:** `Database` owns SQLite connections, `initialize_schema` owns DDL, pure dataclasses represent rows, and repositories own table-specific SQL. `ContextManager` composes repositories and retains all existing context and LangChain business behavior.

**Tech Stack:** Python 3.11, sqlite3, dataclasses, unittest.

## Global Constraints

- Preserve all existing `ContextManager` public method signatures and behavior.
- Preserve existing `messages` and `conversation_contexts` table names, columns, and stored data.
- Models execute no SQL.
- `Database` contains no table or context-domain names.
- Repositories do not contain LangChain or Planner business logic.
- Do not migrate LangGraph checkpoint, ERP, or RAG databases.
- Preserve unrelated dirty working-tree changes.

---

### Task 1: Database Infrastructure and Schema

**Files:**
- Create: `db/__init__.py`
- Create: `db/database.py`
- Create: `db/schema.py`
- Create: `tests/db/__init__.py`
- Create: `tests/db/test_database.py`

**Interfaces:**
- Produces: `Database(db_path: str = "data/chat.db")`
- Produces: `Database.connect() -> sqlite3.Connection`
- Produces: `initialize_schema(database: Database) -> None`

- [ ] **Step 1: Write failing infrastructure tests**

Test with a temporary nested database path that `Database` creates its parent directory, returns a connection with `sqlite3.Row`, enables `PRAGMA foreign_keys`, and that `initialize_schema` creates `messages`, `conversation_contexts`, and `idx_messages_session_id`.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.db.test_database -v
```

Expected: import failure because the `db` package does not exist.

- [ ] **Step 3: Implement Database and schema**

`Database.connect` creates a connection, assigns `sqlite3.Row`, enables foreign keys, and returns it. `initialize_schema` executes the existing DDL without changing columns.

- [ ] **Step 4: Verify GREEN**

Run the same test and expect all cases to pass.

---

### Task 2: Pure Models and Message Repository

**Files:**
- Create: `db/models/__init__.py`
- Create: `db/models/message.py`
- Create: `db/models/conversation_context.py`
- Create: `db/repositories/__init__.py`
- Create: `db/repositories/message_repository.py`
- Create: `tests/db/test_message_repository.py`

**Interfaces:**
- Produces: `Message.from_row(row: sqlite3.Row) -> Message`
- Produces: `ConversationContext.from_row(row: sqlite3.Row) -> ConversationContext`
- Produces: `MessageRepository.save(message: Message) -> int`
- Produces: `MessageRepository.find_by_session(session_id, limit=None, newest_first=False) -> list[Message]`
- Produces: `MessageRepository.delete_by_session(session_id) -> int`
- Produces: `MessageRepository.list_session_ids() -> list[str]`

- [ ] **Step 1: Write failing repository tests**

Initialize a temporary schema and verify message ID creation, oldest/newest ordering, bound positive limit, negative-limit rejection, session deletion count, and unique sorted session IDs.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.db.test_message_repository -v
```

Expected: import failure because models and repository do not exist.

- [ ] **Step 3: Implement pure models and MessageRepository**

Move dataclass conversion behavior from `context/models.py`, add `from_row`, and implement SQL only in the repository. Use fixed ASC/DESC strings selected by a boolean and bind `LIMIT ?`.

- [ ] **Step 4: Verify GREEN**

Run the same test and expect all cases to pass.

---

### Task 3: Conversation Context Repository

**Files:**
- Create: `db/repositories/conversation_context_repository.py`
- Create: `tests/db/test_conversation_context_repository.py`

**Interfaces:**
- Produces: `ConversationContextRepository.get(session_id) -> Optional[ConversationContext]`
- Produces: `ConversationContextRepository.upsert(session_id, context_json, schema_version, last_message_id=None) -> int`
- Produces: `ConversationContextRepository.delete(session_id) -> int`

- [ ] **Step 1: Write failing repository tests**

Verify first upsert returns version 1, second returns 2, omitted `last_message_id` preserves the existing value, returned rows map to `ConversationContext`, and delete returns the affected count.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.db.test_conversation_context_repository -v
```

Expected: import failure because the repository does not exist.

- [ ] **Step 3: Implement ConversationContextRepository**

Move the existing upsert SQL unchanged in behavior, use `ConversationContext.from_row`, and keep each write inside a connection context transaction.

- [ ] **Step 4: Verify GREEN**

Run the same test and expect all cases to pass.

---

### Task 4: Migrate ContextManager and Remove Legacy Persistence

**Files:**
- Modify: `context/manager.py`
- Modify: `context/__init__.py`
- Modify: `tests/context/test_context_storage.py`
- Delete: `context/models.py`
- Delete: `context/sqlite.py`

**Interfaces:**
- Consumes: `Database`, `initialize_schema`, `MessageRepository`, and `ConversationContextRepository`
- Preserves: every existing public `ContextManager` method
- Produces attributes: `message_repository`, `conversation_context_repository`

- [ ] **Step 1: Write failing integration assertions**

Update context storage tests to verify `ContextManager` exposes both repositories, persists/retrieves messages and structured context through them, increments context versions, preserves the last message ID, and clears both tables without using `manager.db`.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.context.test_context_storage -v
```

Expected: failure because the repository attributes are not yet available.

- [ ] **Step 3: Migrate ContextManager**

Construct `Database`, initialize schema, create repositories, replace every `self.db` operation with the appropriate repository, and change imports to `db.models`.

- [ ] **Step 4: Update exports and delete legacy files**

Re-export `Message` and `ConversationContext` from `db.models`, remove `SQLiteManager`, and delete `context/models.py` and `context/sqlite.py`. Confirm no source import remains with:

```bash
rg -n "context\\.models|context\\.sqlite|SQLiteManager|self\\.db" --glob '*.py'
```

- [ ] **Step 5: Verify GREEN**

Run the context tests and expect all cases to pass.

---

### Task 5: Full Verification

**Files:**
- Verify all modified files

**Interfaces:**
- Produces: a persistence layer with stable application behavior

- [ ] **Step 1: Run all database and context tests**

```bash
.venv/bin/python -m unittest discover -s tests/db -t . -v
.venv/bin/python -m unittest discover -s tests/context -t . -v
```

- [ ] **Step 2: Run the complete suite**

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

- [ ] **Step 3: Compile and import**

```bash
.venv/bin/python -m compileall -q agents app context db llm tracing
.venv/bin/python -c 'from app.main import app; from context import ContextManager; from db import Database; print(app.title)'
```

- [ ] **Step 4: Verify structure and diffs**

```bash
rg -n "context\\.models|context\\.sqlite|SQLiteManager|self\\.db" --glob '*.py'
git diff --check
git status --short
```

Expected: no legacy persistence references, clean diff validation, and all unrelated user changes preserved.
