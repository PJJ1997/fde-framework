# Structured Conversation Context Design

## Goal

Replace the Planner's lossy, line-based conversation string with a persisted,
structured context snapshot. The primary goal is to give the Planner resolved
entities, references, constraints, missing information, and trustworthy tool
facts. The secondary goal is to standardize the Planner prompt and reduce
ambiguity.

This first version deliberately uses one SQLite table and one complete JSON
snapshot per session. It does not add an event log or incremental patch store.

## Scope

The change covers:

- a Pydantic schema for structured conversation context;
- one `conversation_contexts` table in the existing chat SQLite database;
- load/save methods on the existing context storage layer;
- one Context Builder LLM call for each new user input;
- deterministic updates from successful tool results;
- JSON serialization of the validated context for the Planner prompt;
- tests for persistence, context generation, and Planner integration.

The change does not cover:

- a context event/audit table;
- semantic retrieval over old conversation messages;
- multiple schema migration versions beyond recognizing `schema_version`;
- a general-purpose memory service shared by every agent type;
- rebuilding context on every Planner/Executor/Reviewer iteration.

## Data Model

### SQLite table

```sql
CREATE TABLE IF NOT EXISTS conversation_contexts (
    session_id TEXT PRIMARY KEY,
    context_json TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    context_version INTEGER NOT NULL DEFAULT 1,
    last_message_id INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`session_id` identifies the conversation. `context_json` stores the latest
validated snapshot. `schema_version` allows future schema recognition.
`context_version` increments on every save. `last_message_id` records the newest
source message included in the snapshot. `updated_at` records the save time.

The original `messages` table remains the source of truth for conversation
history. The context snapshot is derived working memory and may be rebuilt.

### Context JSON

```json
{
  "schema_version": "1.0",
  "current_request": {
    "raw_text": "把刚才那个订单价格改成80",
    "intent": "update_order",
    "is_follow_up": true
  },
  "entities": {
    "orders": {
      "ORD-1001": {
        "order_id": "ORD-1001",
        "customer_name": "张三",
        "product_name": "键盘",
        "quantity": 5,
        "price": 80,
        "address": "上海浦东",
        "source": "conversation"
      }
    }
  },
  "active_entities": {
    "order": "ORD-1001"
  },
  "references": [
    {
      "expression": "刚才那个订单",
      "entity_type": "order",
      "resolved_id": "ORD-1001",
      "status": "resolved"
    }
  ],
  "constraints": [],
  "missing_fields": [],
  "ambiguities": [],
  "tool_facts": [],
  "summary": "用户正在修改订单 ORD-1001 的价格。"
}
```

The schema permits additional entity categories without changing the top-level
shape. Orders are keyed by stable IDs so one conversation can refer to multiple
orders. `active_entities` identifies the current referent for expressions such
as "这个订单".

`current_request.raw_text` preserves the exact current user input.
`references` makes reference resolution explicit rather than silently copying
an inferred value into an entity. `missing_fields` and `ambiguities` remain
separate: a required value may be absent, while an ambiguity has two or more
possible interpretations.

`tool_facts` contains only compact, Planner-relevant facts and identifiers. Full
tool execution data remains in the execution state or future tool-run storage.

## Runtime Flow

For each new user input:

1. Save the raw user message as today.
2. Load the session's existing structured context, if present.
3. Load at most the configured number of recent raw conversation messages.
4. Call the Context Builder LLM with:
   - the previous structured context;
   - the current raw user input;
   - recent messages needed for local reference resolution.
5. Request structured output using the Pydantic context schema.
6. Validate the response and save the complete new snapshot.
7. Serialize the validated snapshot with `model_dump_json()` and give it to the
   Planner as the user-context portion of its prompt.
8. Run Planner, Executor, and Reviewer normally.

The Context Builder runs once per new user input. It does not run again when the
Reviewer requests replanning within the same invocation.

After successful tool execution, deterministic code may update matching entity
fields and append or replace compact `tool_facts`. Tool results do not require a
second Context Builder call and take precedence over conversational inference.

## Context Builder Contract

The Context Builder only interprets context. It must not create an execution
plan or choose tools.

Its prompt requires it to:

- preserve still-valid entities and facts from the previous snapshot;
- use current explicit user values to update conversational values;
- preserve facts whose source is a successful tool result unless a newer tool
  result supersedes them;
- avoid invented values;
- place unresolved references in `ambiguities`;
- place absent required information in `missing_fields`;
- keep `summary` short and factual;
- return only data matching the structured schema.

The implementation should use `with_structured_output(StructuredContext)` and
may use the same validated JSON fallback pattern as the current Planner for
providers that do not support native structured output.

## Planner Prompt

`build_conversation_context()` will no longer create role-prefixed text. It will
return a validated `StructuredContext`, or an empty default context when the
session has no snapshot.

`PlannerNode._build_user_message()` will serialize a single input object:

```json
{
  "context": {},
  "current_user_goal": "...",
  "iteration": 0,
  "review_feedback": null
}
```

On iteration zero, `context.current_request.raw_text` and
`current_user_goal` represent the same user turn by design: the first is part of
the Context Builder's resolved snapshot, while the second remains the explicit
Planner objective. On replanning, the same snapshot is reused and only
`iteration` and `review_feedback` change.

## Persistence API

The existing storage layer will expose:

```python
get_conversation_context(session_id) -> Optional[StructuredContext]
save_conversation_context(
    session_id,
    context,
    last_message_id=None,
) -> int
```

The save operation performs an SQLite upsert and increments
`context_version`. Parsing or validation failure when reading a row is logged
and treated as a missing snapshot so the Context Builder can rebuild it from
recent messages.

Clearing a session deletes both its messages and its structured context.

## Failure Handling

- If no previous snapshot exists, the Context Builder starts from an empty
  schema instance.
- If stored JSON is invalid, it is ignored and rebuilt from recent messages.
- If the Context Builder fails or produces invalid output, the request returns a
  controlled Planner error; it must not silently plan from guessed data.
- If persistence fails, the Planner does not continue with an unpersisted
  context because the next turn would have inconsistent memory.
- Empty conversation history is valid; current user input is sufficient for the
  first Context Builder call.

## Tests

Tests will cover:

- table creation, insert, update/version increment, load, and session deletion;
- Pydantic validation and JSON round-trip;
- first-turn context creation without history;
- follow-up reference resolution using previous context;
- preservation of tool-sourced facts;
- missing and ambiguous information;
- exactly one Context Builder call per user input;
- no Context Builder call during Reviewer-driven replanning;
- Planner input is valid JSON and contains context, goal, iteration, and
  feedback;
- invalid stored JSON triggers rebuild behavior.

## Acceptance Criteria

- Planner no longer receives the old `"用户: ...\n助手: ..."` context string.
- Every new user turn produces and persists one validated context snapshot.
- A follow-up such as "把刚才那个订单价格改成80" can resolve the active order
  and present `order_id` plus the new price to the Planner.
- Replanning reuses the same context snapshot without another Context Builder
  model call.
- Existing raw conversation persistence continues to work.
