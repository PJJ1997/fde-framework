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


if __name__ == "__main__":
    unittest.main()
