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
    def _state(self, decision=ReviewDecision.PASS, feedback="订单详情完整。"):
        return {
            "user_goal": "刚刚我创建了什么订单？",
            "structured_context": StructuredConversationContext(
                active_entities={"order": "ORD-1004"}
            ),
            "planner_result": PlannerResult(
                decision="execute",
                goal="查询刚创建的订单",
                steps=[
                    PlanStep(
                        step_id="step_1",
                        description="查询订单",
                        tool_name="get_order",
                        arguments={"order_id": "ORD-1004"},
                        expected_result="返回订单详情",
                    )
                ],
            ),
            "step_results": [
                StepResult(
                    step_id="step_1",
                    tool_name="get_order",
                    success=True,
                    message="查询到订单 ORD-1004",
                    result={
                        "success": True,
                        "order": {
                            "order_id": "ORD-1004",
                            "product_name": "Azure",
                            "quantity": 10,
                            "price": 5,
                        },
                    },
                )
            ],
            "review_decision": decision,
            "review_feedback": feedback,
        }

    def test_responder_receives_complete_results_and_sets_final_content(self):
        structured_llm = Mock()
        structured_llm.invoke.return_value = ResponderResult(
            content="您刚刚创建的是 ORD-1004，产品为 Azure，数量 10。"
        )
        llm = Mock()
        llm.with_structured_output.return_value = structured_llm
        node = ResponderNode(llm)

        result = node(self._state())

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
        self.assertEqual(
            payload["context"]["active_entities"]["order"],
            "ORD-1004",
        )

    def test_pass_fallback_uses_last_successful_step_message(self):
        structured_llm = Mock()
        structured_llm.invoke.side_effect = RuntimeError("structured failed")
        llm = Mock()
        llm.with_structured_output.return_value = structured_llm
        llm.invoke.side_effect = RuntimeError("json fallback failed")

        result = ResponderNode(llm)(self._state())

        self.assertEqual(result["final_content"], "查询到订单 ORD-1004")

    def test_fail_fallback_uses_review_feedback(self):
        structured_llm = Mock()
        structured_llm.invoke.side_effect = RuntimeError("structured failed")
        llm = Mock()
        llm.with_structured_output.return_value = structured_llm
        llm.invoke.side_effect = RuntimeError("json fallback failed")

        result = ResponderNode(llm)(self._state(
            decision=ReviewDecision.FAIL,
            feedback="没有权限查询该订单。",
        ))

        self.assertEqual(
            result["final_content"],
            "没有权限查询该订单。",
        )


if __name__ == "__main__":
    unittest.main()
