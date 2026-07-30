import json
import unittest
from unittest.mock import Mock

from langgraph.checkpoint.memory import MemorySaver

from agents.planner.nodes.planner_node import PlannerNode
from agents.planner.planner_agent import PlannerAgent
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


if __name__ == "__main__":
    unittest.main()
