import json
import unittest
from unittest.mock import AsyncMock, Mock

from langgraph.checkpoint.memory import MemorySaver

from agents.planner.nodes.executor_node import ExecutorNode
from agents.planner.nodes.planner_node import PlannerNode
from agents.planner.planner_agent import PlannerAgent
from agents.planner.schemas import PlanStep, PlannerResult
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
        agent = PlannerAgent.__new__(PlannerAgent)
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


if __name__ == "__main__":
    unittest.main()
