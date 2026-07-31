# Planner Responder Node Design

## Goal

Add a dedicated Responder node to the Planner workflow so the Reviewer only
evaluates execution results and never generates user-facing content.

## Responsibilities

### Reviewer

The Reviewer receives the user goal, plan, and complete structured execution
results. It returns only an evaluation decision and internal feedback:

- `PASS`: the user goal has been achieved;
- `REPLAN`: the goal has not been achieved, but another executable approach
  may succeed;
- `FAIL`: the goal has not been achieved and execution should stop.

The Reviewer does not populate `final_content`.

### Responder

The Responder receives the complete final workflow state and produces the
single user-facing response. It:

- always attempts one LLM call;
- never selects or invokes tools;
- never creates or modifies an execution plan;
- answers directly from the structured execution results;
- does not invent information absent from the results;
- does not expose internal tool names, node names, parameter names, or review
  mechanics;
- explains the actual failure and a useful next step for terminal failures.

The Responder returns a validated `ResponderResult` containing `content`.

## Graph

```text
ContextBuilder
    |
    v
Planner
    | execute
    v
Executor
    |
    v
Reviewer
    |-- PASS ----> Responder ----> END
    |-- REPLAN --> Planner
    `-- FAIL ----> Responder ----> END
```

Planner decisions `need_input` and `reject` keep their existing direct-to-END
behavior in this first version. Centralizing those responses is outside this
change.

When the maximum iteration count is reached, the Reviewer records a terminal
`FAIL` and routes to the Responder rather than creating final text itself.

## Responder Input

The Responder sends one JSON payload to the LLM:

```json
{
  "user_goal": "刚刚我创建了什么订单？",
  "context": {},
  "plan": {},
  "execution_results": [
    {
      "step_id": "step_1",
      "success": true,
      "message": "查询到订单 ORD-1004",
      "result": {
        "success": true,
        "order": {
          "order_id": "ORD-1004",
          "product_name": "Azure",
          "quantity": 10,
          "price": 5
        }
      }
    }
  ],
  "review": {
    "decision": "PASS",
    "feedback": "订单查询成功并返回完整详情。"
  }
}
```

The payload contains full `StepResult.result` values, not only their human
summary messages.

## Structured Output

```python
class ResponderResult(BaseModel):
    content: str = Field(
        description="Final user-facing response based only on execution results"
    )
```

The Azure/OpenAI integration uses:

```python
llm.with_structured_output(
    ResponderResult,
    method="function_calling",
)
```

This matches the current provider compatibility choice used by ContextBuilder,
Planner, and Reviewer.

## Error Handling

The normal path always attempts one Responder LLM call.

If structured output fails, the Responder attempts the existing validated JSON
fallback. If that call also fails or produces invalid output, it generates a
minimal deterministic response:

- for `PASS`, use the last successful step message, or `任务已完成` when no
  message exists;
- for `FAIL`, use Reviewer feedback, or `任务执行失败` when feedback is empty.

The fallback prevents an otherwise completed workflow from returning an empty
response. It does not make an additional tool call or replan.

## State and Routing

`PlannerState` gains no new long-lived state beyond the `ResponderResult` type;
the Responder writes:

```python
{"final_content": responder_result.content}
```

`route_after_reviewer()` changes to:

- `REPLAN` -> `"planner"`;
- `PASS` or `FAIL` -> `"responder"`.

The graph registers `"responder"` and adds `responder -> END`.

## Tests

Tests cover:

- Reviewer `PASS` routes to Responder;
- Reviewer `FAIL` routes to Responder;
- Reviewer `REPLAN` routes directly to Planner;
- Reviewer no longer writes `final_content`;
- maximum-iteration termination routes through Responder;
- Responder input contains the complete structured execution result;
- Responder uses `method="function_calling"`;
- successful structured output populates `final_content`;
- model failure produces a deterministic non-empty fallback;
- existing ContextBuilder, Planner, Executor, persistence, and Reviewer tests
  continue to pass.

## Acceptance Criteria

- Reviewer never creates user-facing final content.
- PASS and terminal FAIL each invoke the Responder exactly once.
- REPLAN does not invoke the Responder.
- A successful `get_order` result produces a final response containing the
  returned order details rather than Reviewer feedback.
- The workflow always ends with non-empty `final_content` after PASS or FAIL,
  even when the Responder LLM call fails.
