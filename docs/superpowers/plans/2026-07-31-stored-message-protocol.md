# Stable Stored Message Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store conversation history using a project-owned, multimodal `StoredMessage` protocol and isolate all LangChain version dependencies inside a bidirectional adapter.

**Architecture:** Pydantic protocol models define stable JSON messages, the database record stores that JSON with duplicated integrity fields, and `MessageRepository` validates both forms. `ContextManager` converts only at the LangChain boundary and never persists SystemMessage.

**Tech Stack:** Python 3.11, Pydantic 2, LangChain Core messages, sqlite3, unittest.

## Global Constraints

- Do not support the previous LangChain `model_dump()` message payload.
- Do not automatically delete an existing `data/chat.db`.
- Do not persist System Prompt or SystemMessage.
- Support text, URL/Base64 image, referenced file, and JSON content.
- Use project-owned JSON fields only; never use `default=str`.
- Message order is defined by auto-increment `id`.
- LangChain imports are permitted only in the Adapter and Context-facing code, not in `db`.
- Preserve the current StructuredConversationContext storage behavior.
- Preserve unrelated dirty working-tree changes.

---

### Task 1: Stable Protocol Models and Errors

**Files:**
- Create: `db/models/stored_message.py`
- Create: `db/errors.py`
- Modify: `db/models/__init__.py`
- Create: `tests/db/test_stored_message.py`

**Interfaces:**
- Produces: `TextContent`, `ImageContent`, `FileContent`, `JsonContent`
- Produces: discriminated `ContentPart`
- Produces: `StoredToolCall`
- Produces: `StoredMessage`
- Produces: `StoredMessageError`, `UnsupportedStoredMessageError`, `MessageIntegrityError`

- [ ] **Step 1: Write failing protocol tests**

Cover text, URL image, Base64 image, referenced file, JSON content, Assistant Tool Call, Tool result, invalid image/file reference, User Tool Call rejection, Assistant `tool_call_id` rejection, Tool missing `tool_call_id`, System type rejection, and non-JSON metadata rejection.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.db.test_stored_message -v
```

Expected: import failure because `db.models.stored_message` does not exist.

- [ ] **Step 3: Implement protocol models**

Use Pydantic discriminated unions and `model_validator(mode="after")` for cross-field rules. Define recursive JSON value aliases and forbid extra fields so framework-specific fields cannot silently enter the protocol.

- [ ] **Step 4: Verify GREEN**

Run the same test and expect all protocol tests to pass.

---

### Task 2: LangChain Message Adapter

**Files:**
- Create: `context/adapters/__init__.py`
- Create: `context/adapters/langchain_message_adapter.py`
- Create: `tests/context/test_langchain_message_adapter.py`

**Interfaces:**
- Consumes: `StoredMessage` and Content Part models
- Produces: `LangChainMessageAdapter.to_stored(message: BaseMessage) -> StoredMessage`
- Produces: `LangChainMessageAdapter.to_langchain(message: StoredMessage) -> BaseMessage`

- [ ] **Step 1: Write failing adapter tests**

Round-trip Human text, Human text plus image, AI text, AI Tool Calls, Tool text result, and Tool JSON result. Verify SystemMessage, unknown content blocks, invalid tool calls, and unsupported LangChain message classes raise `UnsupportedStoredMessageError`.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.context.test_langchain_message_adapter -v
```

Expected: import failure because the Adapter does not exist.

- [ ] **Step 3: Implement Adapter mappings**

Convert only documented stable fields. Normalize LangChain image URL/data URL blocks into `ImageContent`; reconstruct current LangChain content blocks from the stable representation. Convert ToolMessage dict/list content to `JsonContent` and text to `TextContent`.

- [ ] **Step 4: Verify GREEN**

Run the same test and expect all Adapter tests to pass.

---

### Task 3: Message Table and Repository Integrity

**Files:**
- Modify: `db/schema.py`
- Modify: `db/models/message.py`
- Modify: `db/repositories/message_repository.py`
- Modify: `tests/db/test_database.py`
- Replace expectations in: `tests/db/test_message_repository.py`

**Interfaces:**
- Changes `Message` fields to `session_id`, `message_type`, `payload_json`, `schema_version`, `id`, `created_at`
- Produces: `Message.from_stored(session_id: str, stored: StoredMessage) -> Message`
- Produces: `Message.to_stored() -> StoredMessage`
- Preserves Repository save/find/delete/session-list APIs

- [ ] **Step 1: Write failing schema and repository tests**

Verify the new columns and `idx_messages_session_id_id`; save and restore `StoredMessage`; order by ID; reject database/Payload type mismatch, version mismatch, invalid JSON, and negative limit.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.db.test_database tests.db.test_message_repository -v
```

Expected: failures because the current table and record still use `role` and `content`.

- [ ] **Step 3: Implement the new record and schema**

Replace `role/content` with `message_type/payload_json/schema_version`, change the index, and add schema inspection that raises `MessageIntegrityError` when an existing messages table has the old columns. Never drop the table automatically.

- [ ] **Step 4: Implement Repository validation**

Save the stable record fields and validate `Message.to_stored()` on every read. Order by `id ASC` or `id DESC`, with a bound limit.

- [ ] **Step 5: Verify GREEN**

Run the same tests against temporary fresh databases and expect all cases to pass.

---

### Task 4: ContextManager Integration

**Files:**
- Modify: `context/manager.py`
- Modify: `agents/planner_executor/nodes/context_builder_node.py`
- Modify: `tests/context/test_context_storage.py`
- Modify: `tests/agents/planner/test_context_builder_node.py`
- Create: `tests/context/test_message_history.py`

**Interfaces:**
- ContextManager composes `LangChainMessageAdapter`
- `get_session_history(session_id, limit=None) -> list[StoredMessage]`
- Existing `build`, `save_user_message`, `save_agent_messages`, `get_conversations`, and `clear_session` remain available

- [ ] **Step 1: Write failing ContextManager tests**

Verify saving User/Assistant/Tool messages, skipping SystemMessage, restoring LangChain history, exposing StoredMessage history to Planner, extracting only User/Assistant text for conversation display, preserving multimodal messages, and leaving ToolMessage sanitization behavior unchanged.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.context.test_context_storage tests.context.test_message_history tests.agents.planner.test_context_builder_node -v
```

Expected: failures because ContextManager still serializes `model_dump()` and Planner expects database record fields.

- [ ] **Step 3: Replace serialization with Adapter**

Remove `_MESSAGE_TYPES`, `_deserialize_message`, `_extract_text_content`, and JSON serialization from `_save_langchain_message`. Convert through Adapter and `StoredMessage`; skip SystemMessage before Repository calls.

- [ ] **Step 4: Update Planner Context Builder**

Consume `StoredMessage` directly and render stable protocol JSON in the Context Builder input. Do not convert stored history back into LangChain just to send JSON to the Context Builder LLM.

- [ ] **Step 5: Verify GREEN**

Run the targeted tests and expect all cases to pass.

---

### Task 5: Local Database Cutover and Full Verification

**Files:**
- Verify all changed files
- Local ignored file: `data/chat.db`

**Interfaces:**
- Produces a fresh local message database using schema version 1

- [ ] **Step 1: Detect the local database safely**

Check whether `/Users/jay/workspace/fde-framework/data/chat.db` exists. If it exists, move it to an explicit timestamped backup path under `data/` after user approval; do not delete it.

- [ ] **Step 2: Run database and context tests**

```bash
.venv/bin/python -m unittest discover -s tests/db -t . -v
.venv/bin/python -m unittest discover -s tests/context -t . -v
```

- [ ] **Step 3: Run the complete suite**

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

- [ ] **Step 4: Compile and import**

```bash
.venv/bin/python -m compileall -q agents app context db llm tracing
.venv/bin/python -c 'from app.main import app; from context import ContextManager; from db.models import StoredMessage; print(app.title)'
```

- [ ] **Step 5: Validate dependency boundary and diffs**

```bash
rg -n "langchain" db --glob '*.py'
rg -n "model_dump\\(\\)|default=str|_deserialize_message|_MESSAGE_TYPES" context db --glob '*.py'
git diff --check
git status --short
```

Expected: no LangChain dependency in `db`, no legacy Message serialization, clean diff validation, and unrelated changes preserved.
