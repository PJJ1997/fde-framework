# Structured Conversation Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist one validated structured conversation-context snapshot per session, build it once for every new PlannerAgent user turn, and pass JSON rather than role-prefixed history text to the Planner.

**Architecture:** Add Pydantic context models and store their JSON in one SQLite table managed by the existing `ContextManager`. Add a dedicated `ContextBuilderNode` before the Planner in LangGraph so Reviewer-driven replanning bypasses it. Successful tool results update persisted `tool_facts` deterministically without another model call.

**Tech Stack:** Python 3.11+, Pydantic 2, LangChain 1.x structured output, LangGraph `StateGraph`, SQLite, standard-library `unittest`.

## Global Constraints

- Use exactly one new SQLite table named `conversation_contexts`; do not add an event or patch table.
- Persist one complete JSON snapshot per `session_id`.
- Call the Context Builder LLM exactly once per new user input and never during Reviewer-driven replanning.
- Keep raw conversation messages in the existing `messages` table as the rebuild source.
- Treat successful tool results as more trustworthy than conversational inference and update them without an LLM call.
- Pass validated JSON to the Planner and remove the old role-prefixed conversation string.
- Do not add semantic conversation retrieval or a general memory service.

---

## File Structure

- Create `context/structured.py`: Pydantic models for the persisted JSON.
- Modify `context/sqlite.py`: table creation and raw snapshot CRUD.
- Modify `context/manager.py`: typed context load/save, tool-fact update, and clear-session coordination.
- Modify `context/__init__.py`: export structured-context types.
- Create `agents/planner/nodes/context_builder_node.py`: one LLM extraction call per user turn.
- Modify `agents/planner/schemas.py`: add structured context to `PlannerState`.
- Modify `agents/planner/nodes/__init__.py`: export the new node.
- Modify `agents/planner/nodes/planner_node.py`: consume structured JSON and stop loading history itself.
- Modify `agents/planner/nodes/executor_node.py`: persist successful tool facts deterministically.
- Modify `agents/planner/planner_agent.py`: add the Context Builder as the graph's start node.
- Create `tests/context/test_structured_context.py`: schema and JSON round-trip tests.
- Create `tests/context/test_context_storage.py`: SQLite persistence tests.
- Create `tests/agents/planner/test_context_builder_node.py`: Context Builder behavior tests.
- Create `tests/agents/planner/test_planner_context_integration.py`: graph and Planner prompt integration tests.

---

### Task 1: Define the structured-context schema

**Files:**
- Create: `context/structured.py`
- Modify: `context/__init__.py`
- Test: `tests/context/test_structured_context.py`

**Interfaces:**
- Produces: `StructuredConversationContext.empty() -> StructuredConversationContext`
- Produces: `CurrentRequest`, `ResolvedReference`, and `ToolFact`
- Produces: JSON fields `schema_version`, `current_request`, `entities`, `active_entities`, `references`, `constraints`, `missing_fields`, `ambiguities`, `tool_facts`, and `summary`

- [ ] **Step 1: Write failing schema tests**

```python
import json
import unittest

from context.structured import StructuredConversationContext


class StructuredConversationContextTests(unittest.TestCase):
    def test_empty_context_has_stable_defaults(self):
        context = StructuredConversationContext.empty()
        self.assertEqual(context.schema_version, "1.0")
        self.assertEqual(context.entities, {})
        self.assertEqual(context.tool_facts, [])

    def test_context_round_trips_as_json(self):
        context = StructuredConversationContext.model_validate({
            "schema_version": "1.0",
            "current_request": {
                "raw_text": "把刚才那个订单价格改成80",
                "intent": "update_order",
                "is_follow_up": True,
            },
            "entities": {
                "orders": {
                    "ORD-1001": {"order_id": "ORD-1001", "price": 80}
                }
            },
            "active_entities": {"order": "ORD-1001"},
            "references": [{
                "expression": "刚才那个订单",
                "entity_type": "order",
                "resolved_id": "ORD-1001",
                "status": "resolved",
            }],
            "summary": "用户正在修改订单。",
        })
        restored = StructuredConversationContext.model_validate_json(
            context.model_dump_json()
        )
        self.assertEqual(restored, context)
        self.assertEqual(
            json.loads(context.model_dump_json())["active_entities"]["order"],
            "ORD-1001",
        )
```

- [ ] **Step 2: Run tests and verify the missing module failure**

Run:

```bash
.venv/bin/python -m unittest tests.context.test_structured_context -v
```

Expected: `ModuleNotFoundError: No module named 'context.structured'`.

- [ ] **Step 3: Implement focused Pydantic models**

Create `context/structured.py` with:

```python
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CurrentRequest(BaseModel):
    raw_text: str = ""
    intent: str = ""
    is_follow_up: bool = False


class ResolvedReference(BaseModel):
    expression: str
    entity_type: str
    resolved_id: Optional[str] = None
    status: Literal["resolved", "ambiguous", "unresolved"]


class ToolFact(BaseModel):
    tool: str
    status: Literal["success"] = "success"
    data: Dict[str, Any] = Field(default_factory=dict)


class StructuredConversationContext(BaseModel):
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
        return cls()
```

Export these classes from `context/__init__.py`.

- [ ] **Step 4: Run schema tests**

Run:

```bash
.venv/bin/python -m unittest tests.context.test_structured_context -v
```

Expected: two tests pass.

- [ ] **Step 5: Commit the schema**

```bash
git add context/structured.py context/__init__.py tests/context/test_structured_context.py
git commit -m "feat(context): define structured conversation context"
```

---

### Task 2: Persist one context snapshot per session

**Files:**
- Modify: `context/sqlite.py`
- Modify: `context/manager.py`
- Test: `tests/context/test_context_storage.py`

**Interfaces:**
- Consumes: `StructuredConversationContext`
- Produces: `SQLiteManager.get_conversation_context(session_id: str) -> Optional[dict]`
- Produces: `SQLiteManager.save_conversation_context(session_id: str, context_json: str, schema_version: str, last_message_id: Optional[int]) -> int`
- Produces: `ContextManager.get_structured_context(session_id: str) -> Optional[StructuredConversationContext]`
- Produces: `ContextManager.save_structured_context(session_id: str, context: StructuredConversationContext, last_message_id: Optional[int] = None) -> int`

- [ ] **Step 1: Write failing SQLite storage tests**

```python
import tempfile
import unittest
from pathlib import Path

from context.manager import ContextManager
from context.structured import StructuredConversationContext


class ContextStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = ContextManager(
            str(Path(self.temp_dir.name) / "chat.db")
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_load_and_version_increment(self):
        first = StructuredConversationContext(
            summary="first",
        )
        self.assertEqual(
            self.manager.save_structured_context("session-1", first, 4),
            1,
        )
        second = first.model_copy(update={"summary": "second"})
        self.assertEqual(
            self.manager.save_structured_context("session-1", second, 5),
            2,
        )
        restored = self.manager.get_structured_context("session-1")
        self.assertEqual(restored.summary, "second")

    def test_clear_session_removes_messages_and_context(self):
        self.manager.save_user_message("session-1", "hello")
        self.manager.save_structured_context(
            "session-1", StructuredConversationContext()
        )
        self.manager.clear_session("session-1")
        self.assertIsNone(
            self.manager.get_structured_context("session-1")
        )
        self.assertEqual(
            self.manager.get_session_history("session-1"), []
        )
```

- [ ] **Step 2: Run tests and verify missing methods**

Run:

```bash
.venv/bin/python -m unittest tests.context.test_context_storage -v
```

Expected: failures because `save_structured_context` and
`get_structured_context` do not exist.

- [ ] **Step 3: Add the table and raw SQLite operations**

In `SQLiteManager._init_db()`, create `conversation_contexts` exactly as
specified in the design. Implement an upsert that increments
`context_version`:

```sql
INSERT INTO conversation_contexts (
    session_id, context_json, schema_version, context_version,
    last_message_id, updated_at
) VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
ON CONFLICT(session_id) DO UPDATE SET
    context_json = excluded.context_json,
    schema_version = excluded.schema_version,
    context_version = conversation_contexts.context_version + 1,
    last_message_id = excluded.last_message_id,
    updated_at = CURRENT_TIMESTAMP
```

Return the stored `context_version`. Add raw get and delete methods.

- [ ] **Step 4: Add typed ContextManager operations**

Parse stored JSON using
`StructuredConversationContext.model_validate_json()`. Log invalid stored JSON
and return `None`, so it can be rebuilt. Serialize saves using
`context.model_dump_json()`. Update `clear_session()` to delete both messages
and the context snapshot.

- [ ] **Step 5: Run persistence tests**

Run:

```bash
.venv/bin/python -m unittest tests.context.test_context_storage -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit persistence**

```bash
git add context/sqlite.py context/manager.py tests/context/test_context_storage.py
git commit -m "feat(context): persist structured context snapshots"
```

---

### Task 3: Build context once per new user turn

**Files:**
- Create: `agents/planner/nodes/context_builder_node.py`
- Modify: `agents/planner/nodes/__init__.py`
- Modify: `agents/planner/schemas.py`
- Test: `tests/agents/planner/test_context_builder_node.py`

**Interfaces:**
- Consumes: `PlannerState.session_id`, `PlannerState.user_goal`, existing
  snapshot, and recent messages.
- Produces: `{"structured_context": StructuredConversationContext}`
- Produces: one call to `llm.with_structured_output(StructuredConversationContext).invoke(messages)`

- [ ] **Step 1: Write a failing Context Builder test with a fake structured LLM**

```python
import unittest
from unittest.mock import Mock

from agents.planner.nodes.context_builder_node import ContextBuilderNode
from context.manager import ContextManager
from context.structured import StructuredConversationContext


class ContextBuilderNodeTests(unittest.TestCase):
    def test_builds_and_persists_context_once(self):
        expected = StructuredConversationContext.model_validate({
            "current_request": {
                "raw_text": "价格改成80",
                "intent": "update_order",
                "is_follow_up": True,
            },
            "active_entities": {"order": "ORD-1001"},
            "summary": "修改订单价格。",
        })
        structured = Mock()
        structured.invoke.return_value = expected
        llm = Mock()
        llm.with_structured_output.return_value = structured
        manager = Mock()
        manager.get_structured_context.return_value = None
        manager.get_session_history.return_value = []

        result = ContextBuilderNode(llm, manager)({
            "session_id": "session-1",
            "user_goal": "价格改成80",
        })

        self.assertEqual(result["structured_context"], expected)
        structured.invoke.assert_called_once()
        manager.save_structured_context.assert_called_once()
```

Add tests asserting that previous context and recent messages are represented
as JSON in the Context Builder input and that failure raises instead of
returning guessed context.

- [ ] **Step 2: Run the Context Builder tests and verify the missing module failure**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_context_builder_node -v
```

Expected: `ModuleNotFoundError` for `context_builder_node`.

- [ ] **Step 3: Implement `ContextBuilderNode`**

Constructor:

```python
def __init__(
    self,
    llm: BaseChatModel,
    manager: ContextManager = context_manager,
    max_messages: int = 10,
):
```

Its system prompt must state that it extracts context only, preserves valid old
facts, never plans tools, never invents values, preserves successful
`tool_facts`, and separates missing fields from ambiguities.

Build one JSON user payload:

```python
{
    "previous_context": previous.model_dump(mode="json"),
    "current_user_input": user_goal,
    "recent_messages": [
        {"message_id": message.id, "role": message.role, "content": plain_text}
    ],
}
```

Use structured output first. Reuse `clean_json_response()` plus Pydantic
validation as fallback. Save the resulting complete snapshot with the greatest
recent message ID.

- [ ] **Step 4: Add `structured_context` to `PlannerState` and export the node**

Add:

```python
structured_context: Optional[StructuredConversationContext]
```

Import the type in `schemas.py`, and export `ContextBuilderNode` from
`agents/planner/nodes/__init__.py`.

- [ ] **Step 5: Run Context Builder tests**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_context_builder_node -v
```

Expected: all tests pass and the fake structured LLM is called exactly once.

- [ ] **Step 6: Commit the Context Builder**

```bash
git add agents/planner/nodes/context_builder_node.py agents/planner/nodes/__init__.py agents/planner/schemas.py tests/agents/planner/test_context_builder_node.py
git commit -m "feat(planner): build structured context per user turn"
```

---

### Task 4: Feed JSON context to Planner and prevent rebuilds on replanning

**Files:**
- Modify: `agents/planner/nodes/utils.py`
- Modify: `agents/planner/nodes/planner_node.py`
- Modify: `agents/planner/planner_agent.py`
- Test: `tests/agents/planner/test_planner_context_integration.py`

**Interfaces:**
- Consumes: `PlannerState.structured_context`
- Produces: Planner user-message JSON with `context`, `current_user_goal`,
  `iteration`, and `review_feedback`
- Produces graph edge `START -> context_builder -> planner`
- Preserves reviewer edge `reviewer -> planner` for REPLAN

- [ ] **Step 1: Write failing Planner JSON tests**

```python
import json
import unittest

from agents.planner.nodes.planner_node import PlannerNode
from context.structured import StructuredConversationContext


class PlannerContextIntegrationTests(unittest.TestCase):
    def test_user_message_is_valid_json(self):
        context = StructuredConversationContext(
            active_entities={"order": "ORD-1001"},
            summary="用户正在修改订单。",
        )
        node = PlannerNode.__new__(PlannerNode)
        message = node._build_user_message(
            "把价格改成80", context, 0, ""
        )
        payload = json.loads(message)
        self.assertEqual(
            payload["context"]["active_entities"]["order"],
            "ORD-1001",
        )
        self.assertEqual(payload["current_user_goal"], "把价格改成80")
        self.assertEqual(payload["iteration"], 0)
        self.assertIsNone(payload["review_feedback"])
```

Add a graph topology test by mocking node construction and asserting that the
compiled builder receives `START -> context_builder -> planner`, while
`route_after_reviewer` still maps REPLAN directly to `planner`.

- [ ] **Step 2: Run tests and verify the old string API fails**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_planner_context_integration -v
```

Expected: failure because `_build_user_message()` still accepts a string and
does not produce valid JSON.

- [ ] **Step 3: Replace Planner's string concatenation**

Change `_build_user_message()` to accept
`StructuredConversationContext`. Produce the user message with:

```python
json.dumps({
    "context": conversation_context.model_dump(mode="json"),
    "current_user_goal": user_goal,
    "iteration": iteration,
    "review_feedback": review_feedback or None,
}, ensure_ascii=False)
```

Remove `build_conversation_context()` from `utils.py` and its import from
`planner_node.py`. In `PlannerNode.__call__()`, read
`state.get("structured_context") or StructuredConversationContext.empty()`.

- [ ] **Step 4: Insert Context Builder into the graph**

Instantiate `ContextBuilderNode(self.llm)`, register it as
`"context_builder"`, and change the start edge to:

```python
graph.add_edge(START, "context_builder")
graph.add_edge("context_builder", "planner")
```

Do not modify the Reviewer REPLAN route. Initialize
`"structured_context": None` in `_build_initial_state()`.

- [ ] **Step 5: Run Planner integration tests**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_planner_context_integration -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit Planner integration**

```bash
git add agents/planner/nodes/utils.py agents/planner/nodes/planner_node.py agents/planner/planner_agent.py tests/agents/planner/test_planner_context_integration.py
git commit -m "feat(planner): plan from structured context JSON"
```

---

### Task 5: Persist successful tool facts without another LLM call

**Files:**
- Modify: `context/manager.py`
- Modify: `agents/planner/nodes/executor_node.py`
- Test: `tests/context/test_context_storage.py`
- Test: `tests/agents/planner/test_planner_context_integration.py`

**Interfaces:**
- Produces: `ContextManager.record_tool_facts(session_id: str, step_results: List[StepResult]) -> Optional[StructuredConversationContext]`
- Consumes: successful `StepResult` values only
- Preserves: at most the 20 most recent tool facts

- [ ] **Step 1: Write failing tool-fact tests**

Add a storage test:

```python
from agents.planner.schemas import StepResult

def test_record_tool_facts_keeps_only_successful_results(self):
    self.manager.save_structured_context(
        "session-1", StructuredConversationContext()
    )
    updated = self.manager.record_tool_facts("session-1", [
        StepResult(
            step_id="step_1",
            tool_name="update_order",
            success=True,
            result={"order": {"order_id": "ORD-1001", "price": 80}},
            message="updated",
        ),
        StepResult(
            step_id="step_2",
            tool_name="missing_tool",
            success=False,
            result={"error": "failed"},
            message="failed",
        ),
    ])
    self.assertEqual(len(updated.tool_facts), 1)
    self.assertEqual(updated.tool_facts[0].tool, "update_order")
```

Add an Executor test with a mocked manager and confirm
`record_tool_facts()` is called once after execution and no LLM is involved.

- [ ] **Step 2: Run focused tests and verify the missing method failure**

Run:

```bash
.venv/bin/python -m unittest tests.context.test_context_storage tests.agents.planner.test_planner_context_integration -v
```

Expected: failure because `record_tool_facts()` does not exist.

- [ ] **Step 3: Implement deterministic tool-fact updates**

Load the current snapshot; return `None` if it does not exist. Convert each
successful result to:

```python
ToolFact(
    tool=step.tool_name,
    status="success",
    data=step.result,
)
```

Append facts, keep the last 20, and save the updated complete snapshot. Do not
invoke an LLM.

- [ ] **Step 4: Call the update once from ExecutorNode**

Inject `ContextManager` into `ExecutorNode` with the module singleton as the
default. The current node calls a nonexistent `executor.execute_tool()` method;
replace it with the executor's actual async interface while this file is under
test:

```python
self.executor = executor

result = asyncio.run(
    self.executor.execute(
        tool,
        step.arguments,
        context={"session_id": session_id},
    )
)
```

After all steps finish:

```python
self.context_manager.record_tool_facts(session_id, step_results)
```

Only this manager method filters successful results.

- [ ] **Step 5: Run all tests**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Run syntax and import verification**

Run:

```bash
.venv/bin/python -m compileall -q app agents context llm prompts rag tools tracing
.venv/bin/python -c "from app.main import app; print(app.title)"
```

Expected: compile command exits 0 and import prints `FDE Framework`.

- [ ] **Step 7: Commit tool facts and final integration**

```bash
git add context/manager.py agents/planner/nodes/executor_node.py tests/context/test_context_storage.py tests/agents/planner/test_planner_context_integration.py
git commit -m "feat(planner): persist successful tool facts"
```
