import json
import unittest
from unittest.mock import Mock

from agents.planner_executor.nodes.context_builder_node import ContextBuilderNode
from db.models import StoredMessage, TextContent
from context.structured import CurrentRequest, StructuredConversationContext


class ContextBuilderNodeTests(unittest.TestCase):
    def _make_llm(self, result):
        structured = Mock()
        structured.invoke.return_value = result
        llm = Mock()
        llm.with_structured_output.return_value = structured
        return llm, structured

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
        llm, structured = self._make_llm(expected)
        manager = Mock()
        manager.get_structured_context.return_value = None
        manager.get_session_history.return_value = []
        manager.get_last_message_id.return_value = None

        result = ContextBuilderNode(llm, manager)({
            "session_id": "session-1",
            "user_goal": "价格改成80",
        })

        self.assertEqual(result["structured_context"], expected)
        structured.invoke.assert_called_once()
        manager.save_structured_context.assert_called_once_with(
            "session-1", expected, last_message_id=None
        )

    def test_input_contains_previous_context_and_recent_messages_as_json(self):
        previous = StructuredConversationContext(
            active_entities={"order": "ORD-1001"},
            summary="已创建订单。",
        )
        expected = previous.model_copy(update={
            "current_request": CurrentRequest(
                raw_text="这个订单多少钱",
                intent="get_order",
                is_follow_up=True,
            )
        })
        llm, structured = self._make_llm(expected)
        manager = Mock()
        manager.get_structured_context.return_value = previous
        manager.get_session_history.return_value = [
            StoredMessage(
                message_type="user",
                content=[TextContent(text="刚创建了订单")],
            )
        ]
        manager.get_last_message_id.return_value = 9

        ContextBuilderNode(llm, manager)({
            "session_id": "session-1",
            "user_goal": "这个订单多少钱",
        })

        messages = structured.invoke.call_args.args[0]
        payload = json.loads(messages[1].content)
        self.assertEqual(
            payload["previous_context"]["active_entities"]["order"],
            "ORD-1001",
        )
        self.assertEqual(
            payload["recent_messages"][0]["content"][0]["text"],
            "刚创建了订单",
        )
        self.assertEqual(
            payload["recent_messages"][0]["message_type"],
            "user",
        )
        manager.save_structured_context.assert_called_once_with(
            "session-1", expected, last_message_id=9
        )

    def test_builder_failure_is_not_replaced_with_guessed_context(self):
        llm = Mock()
        structured = Mock()
        structured.invoke.side_effect = RuntimeError("model unavailable")
        llm.with_structured_output.return_value = structured
        llm.invoke.side_effect = RuntimeError("fallback unavailable")
        manager = Mock()
        manager.get_structured_context.return_value = None
        manager.get_session_history.return_value = []
        manager.get_last_message_id.return_value = None

        with self.assertRaises(RuntimeError):
            ContextBuilderNode(llm, manager)({
                "session_id": "session-1",
                "user_goal": "创建订单",
            })

        manager.save_structured_context.assert_not_called()


if __name__ == "__main__":
    unittest.main()
