# Planner Responder Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-LLM Responder node that owns user-facing output while Reviewer remains evaluation-only.

**Architecture:** Introduce `ResponderResult` and `ResponderNode`, route terminal Reviewer decisions to the new node, and keep only `REPLAN` connected to Planner. The Responder consumes one structured JSON payload containing context, plan, full execution results, and review feedback, then writes `final_content`.

**Tech Stack:** Python 3.11+, Pydantic 2, LangChain structured output with `method="function_calling"`, LangGraph `StateGraph`, standard-library `unittest`.

## Global Constraints

- Responder always attempts one LLM call on terminal Reviewer decisions.
- Reviewer never writes user-facing `final_content`.
- `PASS` and `FAIL` route to Responder; only `REPLAN` routes to Planner.
- Planner `need_input` and `reject` behavior remains unchanged.
- Responder receives complete `StepResult.result` data.
- Responder cannot call tools or create plans.
- Preserve all existing uncommitted Azure/provider and logging changes.

---

## File Structure

- Modify `agents/planner/schemas.py`: add `ResponderResult`.
- Create `agents/planner/nodes/responder_node.py`: construct JSON input, call LLM, and provide deterministic fallback.
- Modify `agents/planner/nodes/__init__.py`: export `ResponderNode`.
- Modify `agents/planner/nodes/reviewer_node.py`: remove all `final_content` generation.
- Modify `agents/planner/nodes/routes.py`: route terminal review decisions to Responder.
- Modify `agents/planner/planner_agent.py`: register Responder and connect it to END.
- Create `tests/agents/planner/test_responder_node.py`: node behavior and fallback tests.
- Modify `tests/agents/planner/test_planner_context_integration.py`: Reviewer routing and graph topology tests.

---

### Task 1: Define and implement ResponderNode

**Files:**
- Modify: `agents/planner/schemas.py`
- Create: `agents/planner/nodes/responder_node.py`
- Modify: `agents/planner/nodes/__init__.py`
- Create: `tests/agents/planner/test_responder_node.py`

**Interfaces:**
- Produces: `ResponderResult(content: str)`
- Produces: `ResponderNode(llm: BaseChatModel)`
- Consumes: `PlannerState.user_goal`, `structured_context`, `planner_result`, `step_results`, `review_decision`, and `review_feedback`
- Produces: `{"final_content": str}`

- [ ] **Step 1: Write failing successful-response test**

```python
import json
import unittest
from unittest.mock import Mock

from agents.planner.nodes.responder_node import ResponderNode
from agents.planner.schemas import (
    PlanStep,
    PlannerResult,
    ResponderResult,
    ReviewDecision,
    StepResult,
)
from context.structured import StructuredConversationContext


class ResponderNodeTests(unittest.TestCase):
    def test_responder_receives_complete_results_and_sets_final_content(self):
        structured_llm = Mock()
        structured_llm.invoke.return_value = ResponderResult(
            content="您刚刚创建的是 ORD-1004，产品为 Azure，数量 10。"
        )
        llm = Mock()
        llm.with_structured_output.return_value = structured_llm
        node = ResponderNode(llm)
        state = {
            "user_goal": "刚刚我创建了什么订单？",
            "structured_context": StructuredConversationContext(),
            "planner_result": PlannerResult(
                decision="execute",
                goal="查询刚创建的订单",
                steps=[PlanStep(
                    step_id="step_1",
                    description="查询订单",
                    tool_name="get_order",
                    arguments={"order_id": "ORD-1004"},
                    expected_result="返回订单详情",
                )],
            ),
            "step_results": [StepResult(
                step_id="step_1",
                tool_name="get_order",
                success=True,
                message="查询到订单 ORD-1004",
                result={"order": {
                    "order_id": "ORD-1004",
                    "product_name": "Azure",
                    "quantity": 10,
                }},
            )],
            "review_decision": ReviewDecision.PASS,
            "review_feedback": "订单详情完整。",
        }

        result = node(state)

        self.assertEqual(
            result["final_content"],
            "您刚刚创建的是 ORD-1004，产品为 Azure，数量 10。",
        )
        llm.with_structured_output.assert_called_once_with(
            ResponderResult,
            method="function_calling",
        )
        messages = structured_llm.invoke.call_args.args[0]
        payload = json.loads(messages[1].content)
        self.assertEqual(
            payload["execution_results"][0]["result"]["order"]["order_id"],
            "ORD-1004",
        )
```

- [ ] **Step 2: Run the test and verify missing module failure**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_responder_node.ResponderNodeTests.test_responder_receives_complete_results_and_sets_final_content -v
```

Expected: `ModuleNotFoundError` for `responder_node`.

- [ ] **Step 3: Add `ResponderResult`**

In `schemas.py`:

```python
class ResponderResult(BaseModel):
    content: str = Field(
        description="Final user-facing response based only on execution results"
    )
```

- [ ] **Step 4: Implement ResponderNode's structured path**

Create a node that builds this JSON payload:

```python
{
    "user_goal": state.get("user_goal", ""),
    "context": context.model_dump(mode="json"),
    "plan": planner_result.model_dump(mode="json") if planner_result else None,
    "execution_results": [
        step.model_dump(mode="json") for step in step_results
    ],
    "review": {
        "decision": decision.value if decision else "FAIL",
        "feedback": state.get("review_feedback", ""),
    },
}
```

Use a SystemMessage that prohibits tools, planning, invented facts, and internal
implementation details. Call:

```python
self.llm.with_structured_output(
    ResponderResult,
    method="function_calling",
)
```

Return `{"final_content": result.content}`.

- [ ] **Step 5: Write failing fallback tests**

Add two tests:

```python
def test_pass_fallback_uses_last_successful_step_message(self):
    # structured and JSON fallback calls both raise
    # expected final_content == "查询到订单 ORD-1004"

def test_fail_fallback_uses_review_feedback(self):
    # structured and JSON fallback calls both raise
    # expected final_content == review_feedback
```

Use `Mock.side_effect` to make both model paths fail.

- [ ] **Step 6: Run fallback tests and verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_responder_node -v
```

Expected: fallback tests fail because fallback behavior is absent.

- [ ] **Step 7: Implement validated JSON fallback and deterministic last fallback**

On structured failure, call the base LLM once and parse
`ResponderResult.model_validate_json(clean_json_response(response.content))`.
If that also fails:

- PASS: return the last successful step message, otherwise `任务已完成`;
- FAIL: return non-empty review feedback, otherwise `任务执行失败`.

- [ ] **Step 8: Run Responder tests**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_responder_node -v
```

Expected: all Responder tests pass.

---

### Task 2: Make Reviewer evaluation-only and update routing

**Files:**
- Modify: `agents/planner/nodes/reviewer_node.py`
- Modify: `agents/planner/nodes/routes.py`
- Modify: `agents/planner/planner_agent.py`
- Modify: `tests/agents/planner/test_planner_context_integration.py`

**Interfaces:**
- Consumes: existing `ReviewDecision`
- Produces: `route_after_reviewer(state) -> "planner" | "responder"`
- Produces graph edges `reviewer -> planner`, `reviewer -> responder`, and `responder -> END`

- [ ] **Step 1: Write failing Reviewer separation tests**

Add tests:

```python
def test_reviewer_pass_does_not_write_final_content(self):
    # mock _call_llm_with_fallback to return PASS and feedback
    # assert "final_content" not in result

def test_reviewer_fail_does_not_write_final_content(self):
    # mock _call_llm_with_fallback to return FAIL and feedback
    # assert "final_content" not in result

def test_max_iterations_returns_terminal_review_without_content(self):
    # iteration_count == max_iterations
    # assert decision == FAIL and "final_content" not in result
```

- [ ] **Step 2: Write failing routing tests**

Assert:

```python
self.assertEqual(
    route_after_reviewer({"review_decision": ReviewDecision.PASS}),
    "responder",
)
self.assertEqual(
    route_after_reviewer({"review_decision": ReviewDecision.FAIL}),
    "responder",
)
self.assertEqual(
    route_after_reviewer({"review_decision": ReviewDecision.REPLAN}),
    "planner",
)
```

- [ ] **Step 3: Run focused tests and verify current behavior fails**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_planner_context_integration -v
```

Expected: terminal decisions still route to END and Reviewer still writes
`final_content`.

- [ ] **Step 4: Remove final-content generation from Reviewer**

For normal PASS, REPLAN, and FAIL results return only:

```python
{
    "review_decision": decision,
    "review_feedback": feedback,
}
```

For max iteration and missing-plan terminal results, return evaluation fields
only. Remove `extract_final_answer` from Reviewer imports and logic.

- [ ] **Step 5: Update route and graph**

Change `route_after_reviewer()`:

```python
if decision == ReviewDecision.REPLAN:
    return "planner"
return "responder"
```

Register `ResponderNode(self.llm)`, add it to the graph, map terminal Reviewer
decisions to `"responder"`, and add:

```python
graph.add_edge("responder", END)
```

- [ ] **Step 6: Run routing and graph tests**

Run:

```bash
.venv/bin/python -m unittest tests.agents.planner.test_planner_context_integration -v
```

Expected: all tests pass.

---

### Task 3: Full verification without overwriting user changes

**Files:**
- Test: `tests/agents/planner/test_responder_node.py`
- Test: `tests/agents/planner/test_planner_context_integration.py`
- Verify only: user-owned Azure/provider and logging changes

**Interfaces:**
- Verifies the complete Planner workflow contract.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

Expected: all tests pass.

- [ ] **Step 2: Run compilation and import checks**

Run:

```bash
.venv/bin/python -m compileall -q agents context
.venv/bin/python -c "from agents.planner.nodes.responder_node import ResponderNode; from app.main import app; print(app.title)"
```

Expected: both commands exit 0 and import prints `FDE Framework`.

- [ ] **Step 3: Check diffs and preserve user-owned changes**

Run:

```bash
git diff --check
git status --short
```

Confirm the Azure provider, provider selection, `function_calling`, and
ContextBuilder logging changes remain present. Do not stage or commit them
without explicit user approval.

