import json
import unittest
from unittest.mock import AsyncMock, Mock

from langgraph.checkpoint.memory import MemorySaver

from agents.planner_executor.nodes.executor_node import ExecutorNode
from agents.planner_executor.nodes.planner_node import PlannerNode
from agents.planner_executor.nodes.reviewer_node import ReviewerNode
from agents.planner_executor.nodes.routes import route_after_reviewer
from agents.planner_executor.planner_executor_agent import PlannerExecutorAgent
from agents.planner_executor.schemas import (
    PlanStep,
    PlannerResult,
    ReviewDecision,
    ReviewResult,
    StepResult,
)
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

    def test_graph_builds_context_once_before_planning(self):
        agent = PlannerExecutorAgent.__new__(PlannerExecutorAgent)
        agent.llm = Mock()
        agent.max_iterations = 3
        agent._checkpointer = MemorySaver()
        agent._tools = {}

        graph = agent._build_graph().get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn(("__start__", "context_builder"), edges)
        self.assertIn(("context_builder", "planner"), edges)
        self.assertNotIn(("reviewer", "context_builder"), edges)
        self.assertIn(("reviewer", "planner"), edges)

    def test_graph_routes_review_completion_through_responder(self):
        agent = PlannerExecutorAgent.__new__(PlannerExecutorAgent)
        agent.llm = Mock()
        agent.max_iterations = 3
        agent._checkpointer = MemorySaver()
        agent._tools = {}

        graph = agent._build_graph().get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn(("reviewer", "responder"), edges)
        self.assertIn(("responder", "__end__"), edges)
        self.assertIn(("reviewer", "planner"), edges)
        self.assertNotIn(("reviewer", "__end__"), edges)

    def test_reviewer_route_sends_pass_and_fail_to_responder(self):
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

    def test_executor_persists_tool_facts_without_llm(self):
        tool = Mock()
        tool_executor = Mock()
        tool_executor.execute = AsyncMock(return_value={
            "order": {"order_id": "ORD-1001", "price": 80},
            "message": "updated",
        })
        manager = Mock()
        node = ExecutorNode(
            {"update_order": tool},
            context_manager_instance=manager,
            tool_executor=tool_executor,
        )
        state = {
            "session_id": "session-1",
            "planner_result": PlannerResult(
                decision="execute",
                goal="修改订单价格",
                steps=[
                    PlanStep(
                        step_id="step_1",
                        description="修改价格",
                        tool_name="update_order",
                        arguments={"order_id": "ORD-1001", "price": 80},
                        expected_result="价格修改成功",
                    )
                ],
            ),
        }

        result = node(state)

        self.assertTrue(result["step_results"][0].success)
        tool_executor.execute.assert_awaited_once()
        manager.record_tool_facts.assert_called_once_with(
            "session-1", result["step_results"]
        )

    def test_reviewer_receives_complete_structured_tool_result(self):
        reviewer = ReviewerNode(Mock())
        step_results = [
            StepResult(
                step_id="step_1",
                tool_name="get_order",
                success=True,
                message="查询到订单 ORD-1004",
                result={
                    "success": True,
                    "order": {
                        "order_id": "ORD-1004",
                        "product_name": "键盘",
                        "quantity": 2,
                        "price": 100,
                    },
                },
            )
        ]

        results_json, all_success = reviewer._build_results_summary(
            step_results
        )
        payload = json.loads(results_json)

        self.assertTrue(all_success)
        self.assertEqual(
            payload[0]["result"]["order"]["order_id"],
            "ORD-1004",
        )
        self.assertEqual(
            payload[0]["result"]["order"]["product_name"],
            "键盘",
        )

    def test_reviewer_only_returns_evaluation(self):
        structured_llm = Mock()
        structured_llm.invoke.return_value = ReviewResult(
            decision="PASS",
            feedback="订单详情完整。",
        )
        llm = Mock()
        llm.with_structured_output.return_value = structured_llm
        reviewer = ReviewerNode(llm)
        state = {
            "user_goal": "查询订单",
            "planner_result": PlannerResult(
                decision="execute",
                goal="查询订单",
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
                    result={"order": {"order_id": "ORD-1004"}},
                )
            ],
            "iteration_count": 1,
            "max_iterations": 3,
        }

        result = reviewer(state)

        self.assertEqual(result["review_decision"], ReviewDecision.PASS)
        self.assertNotIn("final_content", result)

    def test_reviewer_max_iterations_does_not_generate_user_content(self):
        result = ReviewerNode(Mock())({
            "iteration_count": 3,
            "max_iterations": 3,
        })

        self.assertEqual(result["review_decision"], ReviewDecision.FAIL)
        self.assertNotIn("final_content", result)

    def test_executor_marks_returned_business_error_as_failed(self):
        tool = Mock()
        tool_executor = Mock()
        tool_executor.execute = AsyncMock(return_value={
            "success": False,
            "error": "订单 ORD-404 不存在",
        })
        manager = Mock()
        node = ExecutorNode(
            {"get_order": tool},
            context_manager_instance=manager,
            tool_executor=tool_executor,
        )
        state = {
            "session_id": "session-1",
            "planner_result": PlannerResult(
                decision="execute",
                goal="查询订单",
                steps=[
                    PlanStep(
                        step_id="step_1",
                        description="查询订单",
                        tool_name="get_order",
                        arguments={"order_id": "ORD-404"},
                        expected_result="返回订单详情",
                    )
                ],
            ),
        }

        result = node(state)

        self.assertFalse(result["step_results"][0].success)
        self.assertEqual(
            result["step_results"][0].message,
            "订单 ORD-404 不存在",
        )


if __name__ == "__main__":
    unittest.main()
