"""Workflow node functions for the order workflow.

Each method on WorkflowNodes is a LangGraph node. Tools are injected via the
constructor so every tool call goes through ToolExecutor's middleware chain.
"""
import asyncio
from typing import Dict, List, TypedDict

from langchain_core.messages import BaseMessage
from langchain_core.tools import StructuredTool
from langgraph.types import interrupt

from tools.executor import executor


class WorkflowState(TypedDict, total=False):
    """State for the order workflow."""

    session_id: str
    customer_name: str
    product_name: str
    quantity: int
    price: float
    new_price: float
    address: str
    order_id: str
    user_confirmed: bool
    step_results: List[dict]
    messages: List[BaseMessage]


class WorkflowNodes:
    """LangGraph node functions for the order workflow.

    Tools are injected so all tool calls go through the executor's middleware
    chain. Node methods are bound directly to the graph; should_create is a
    static conditional-edge router.
    """

    def __init__(self, tools: Dict[str, StructuredTool]):
        self.tools = tools

    def _run_tool_step(
        self, state: WorkflowState, tool_name: str, args: dict, label: str
    ) -> tuple:
        """Call a tool via executor and return (result, step_update).

        Centralizes the executor.execute + step_results template so each tool
        node only declares its args. Returns the raw executor result (for nodes
        that need to extract fields) and a state update dict containing the
        appended step_results entry.
        """
        result = asyncio.run(
            executor.execute(
                self.tools[tool_name],
                args,
                context={"session_id": state["session_id"]}
            )
        )
        # Tools return {"message": ...} on success but {"error": ...} on
        # failure; fall back so a missing key never raises KeyError.
        text = result.get("message") or result.get("error") or "执行完成"
        update = {
            "step_results": state.get("step_results", [])
            + [{"role": "assistant", "content": f"{label}: {text}"}]
        }
        return result, update

    def confirm_create(self, state: WorkflowState) -> dict:
        """Step 1: Interrupt to ask for confirmation before creating.

        Uses LangGraph's interrupt() for workflow-level confirmation.
        """
        user_decision = interrupt({
            "customer_name": state["customer_name"],
            "product_name": state["product_name"],
            "quantity": state["quantity"],
            "price": state["price"],
            "message": (
                f"确认要创建订单吗？客户: {state['customer_name']}, "
                f"产品: {state['product_name']}, 数量: {state['quantity']}, "
                f"价格: {state['price']}"
            ),
        })
        confirmed = False
        if isinstance(user_decision, dict):
            confirmed = user_decision.get("confirmed", False)
        elif isinstance(user_decision, bool):
            confirmed = user_decision

        return {
            "user_confirmed": confirmed,
            "step_results": state.get("step_results", [])
            + [{"role": "user", "content": f"confirm_create: {'confirmed' if confirmed else 'cancelled'}"}],
        }

    @staticmethod
    def should_create(state: WorkflowState) -> str:
        """Conditional edge: route based on user confirmation."""
        return "create" if state.get("user_confirmed", False) else "end"

    def create_order(self, state: WorkflowState) -> dict:
        """Step 2: Create an order via executor (middleware chain runs)."""
        result, update = self._run_tool_step(
            state,
            "create_order",
            {
                "customer_name": state["customer_name"],
                "product_name": state["product_name"],
                "quantity": state["quantity"],
                "price": state["price"],
                "address": state["address"],
            },
            "create_order",
        )
        update["order_id"] = result.get("order", {}).get("order_id", "")
        return update

    def modify_price(self, state: WorkflowState) -> dict:
        """Step 3: Modify the order price via executor."""
        _, update = self._run_tool_step(
            state,
            "update_order",
            {"order_id": state["order_id"], "price": state["new_price"]},
            "modify_price",
        )
        return update

    def delete_order(self, state: WorkflowState) -> dict:
        """Step 4: Delete the order via executor (middleware chain runs)."""
        _, update = self._run_tool_step(
            state,
            "delete_order",
            {"order_id": state["order_id"]},
            "delete_order",
        )
        return update
