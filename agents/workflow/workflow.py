"""Workflow Agent using LangGraph.

Implements an order workflow: confirm_create (interrupt) → create_order → modify_price → delete_order.
Uses LangGraph's interrupt/resume for the confirmation step before order creation.

All tool calls go through ToolExecutor's middleware chain via executor.execute().

Note: Uses sync graph.invoke/stream wrapped in asyncio.to_thread because
interrupt() requires Python 3.11+ for async usage (contextvar propagation).
On Python 3.10, sync mode in a separate thread works correctly.
"""
import asyncio
import uuid
from pathlib import Path
from typing import Any, List, AsyncIterator, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from agents.base import BaseAgent, AgentInput, AgentResult
from context import context_manager
from tools.registry import registry
from .nodes import WorkflowState, WorkflowNodes

# Sentinel for detecting iterator exhaustion without raising StopIteration.
# PEP 479 converts StopIteration to RuntimeError inside async generators,
# so we use next(iterator, _SENTINEL) instead of try/except StopIteration.
_SENTINEL = object()


class WorkflowAgent(BaseAgent):
    """Workflow Agent - structured multi-step agent using LangGraph.

    Implements an order workflow: confirm_create (interrupt) → create_order →
    modify_price → delete_order.

    All tool calls go through ToolExecutor's middleware chain.
    Uses LangGraph's interrupt/resume for the confirmation step:
    - invoke/stream pauses at confirm_create via interrupt()
    - resume() continues after user provides resume_data
    """

    # Process-wide MemorySaver singleton used when SqliteSaver is unavailable.
    # Sharing one MemorySaver across instances lets invoke (chat) and resume
    # (actions) share state by thread_id within the same process.
    _shared_memory_saver = None

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self._checkpointer = self._build_checkpointer()
        self._tools = {t.name: t for t in registry.get_tools()}
        self._graph = self._build_graph()

    @classmethod
    def _build_checkpointer(cls):
        """Build a checkpointer shared across WorkflowAgent instances.

        Preferred: SqliteSaver (persistent on disk, cross-process) when the
        optional langgraph-checkpoint-sqlite package is installed — each
        instance gets its own saver/conn but shares state via the same db
        file. Falls back to a process-wide MemorySaver singleton so invoke
        (chat) and resume (actions) share state across instances within one
        process.
        """
        try:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver

            db_path = Path("data/workflow.db")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            saver = SqliteSaver(conn)
            saver.setup()
            return saver
        except ImportError:
            if cls._shared_memory_saver is None:
                from langgraph.checkpoint.memory import MemorySaver
                cls._shared_memory_saver = MemorySaver()
            return cls._shared_memory_saver

    def _build_graph(self):
        """Build and compile the workflow graph.

        Node functions live in WorkflowNodes (nodes.py); tools are injected so
        every tool call goes through the executor's middleware chain.
        """
        nodes = WorkflowNodes(self._tools)

        graph = StateGraph(WorkflowState)
        graph.add_node("confirm_create", nodes.confirm_create)
        graph.add_node("create_order", nodes.create_order)
        graph.add_node("modify_price", nodes.modify_price)
        graph.add_node("delete_order", nodes.delete_order)

        graph.add_edge(START, "confirm_create")
        graph.add_conditional_edges(
            "confirm_create",
            WorkflowNodes.should_create,
            {"create": "create_order", "end": END},
        )
        graph.add_edge("create_order", "modify_price")
        graph.add_edge("modify_price", "delete_order")
        graph.add_edge("delete_order", END)

        return graph.compile(checkpointer=self._checkpointer)

    def _build_initial_state(self, input: AgentInput) -> dict:
        """Build workflow state from AgentInput.

        Merges input.state (business params from caller) with defaults. The
        caller is responsible for parsing user input into state; workflow
        only fills defaults for missing fields.
        """
        session_id = input.session_id or str(uuid.uuid4())
        state = {
            "session_id": session_id,
            "customer_name": "测试客户",
            "product_name": "测试产品",
            "quantity": 1,
            "price": 100.0,
            "new_price": 80.0,
            "address": "测试地址",
            "order_id": "",
            "user_confirmed": False,
            "step_results": [],
            "messages": input.messages,
        }
        if input.state:
            state.update(input.state)
        return state

    def _get_interrupt_value(self, config: dict) -> Optional[dict]:
        """Extract the interrupt value from the graph state if interrupted."""
        state = self._graph.get_state(config)
        if not state.next:
            return None
        for task in state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                return task.interrupts[0].value
        return {}

    def _build_confirmation(self, session_id: str, thread_id: str) -> dict:
        """Build confirmation metadata for frontend (no tool info exposed)."""
        return {
            "type": "confirmation_required",
            "session_id": session_id,
            "thread_id": thread_id,
        }

    def _get_interrupt_message(self, interrupt_value: dict) -> str:
        """Extract a human-readable message from the interrupt value."""
        if isinstance(interrupt_value, dict):
            return interrupt_value.get("message", "需要用户确认")
        return "需要用户确认"

    def _step_to_message(self, item: dict) -> BaseMessage:
        """Convert a step_result dict to a message with appropriate role.

        Each step_result is {"role": "user"|"assistant", "content": str}.
        The role is decided by the node that produced it, so this method
        never needs to know specific node names.
        """
        if item.get("role") == "user":
            return HumanMessage(content=item.get("content", ""))
        return AIMessage(content=item.get("content", ""))

    async def invoke(self, input: AgentInput) -> AgentResult:
        """Invoke the workflow.

        Uses a unique thread_id per invocation so interrupted states are
        preserved independently and don't block subsequent invocations.
        """
        initial_state = self._build_initial_state(input)
        messages = input.messages
        session_id = initial_state["session_id"]
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        result = await asyncio.to_thread(
            self._graph.invoke, initial_state, config=config
        )

        # Persist step_results as messages. Initial state had an empty
        # step_results list, so everything here is newly produced.
        step_results = result.get("step_results", [])
        if step_results:
            msgs = [self._step_to_message(s) for s in step_results]
            context_manager.save_agent_messages(session_id, msgs)

        # Check if interrupted
        interrupt_value = await asyncio.to_thread(self._get_interrupt_value, config)
        if interrupt_value is not None:
            return AgentResult(
                content=self._get_interrupt_message(interrupt_value),
                session_id=session_id,
                confirmation=self._build_confirmation(session_id, thread_id),
            )

        # Completed normally
        content = "\n".join(s["content"] for s in step_results) if step_results else "工作流执行完成"
        return AgentResult(content=content, session_id=session_id)

    async def stream(self, input: AgentInput) -> AsyncIterator[Any]:
        """Stream the workflow execution.

        Uses a unique thread_id per invocation.
        """
        initial_state = self._build_initial_state(input)
        messages = input.messages
        session_id = initial_state["session_id"]
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        iterator = iter(self._graph.stream(initial_state, config=config))

        new_step_items = []
        while True:
            step = await asyncio.to_thread(next, iterator, _SENTINEL)
            if step is _SENTINEL:
                break
            # step_results are cumulative across nodes; capture only the
            # newly appended entry from each node output.
            for node_output in step.values():
                if isinstance(node_output, dict) and node_output.get("step_results"):
                    new_step_items.append(node_output["step_results"][-1])
            yield step

        # Persist new step results as messages
        if new_step_items:
            msgs = [self._step_to_message(s) for s in new_step_items]
            context_manager.save_agent_messages(session_id, msgs)

        # Check if interrupted
        interrupt_value = await asyncio.to_thread(self._get_interrupt_value, config)
        if interrupt_value is not None:
            yield AgentResult(
                content=self._get_interrupt_message(interrupt_value),
                session_id=session_id,
                confirmation=self._build_confirmation(session_id, thread_id),
            )

    async def resume(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Resume the workflow after an interrupt.

        Args:
            thread_id: The thread_id from the confirmation response.
            resume_data: Resume format from agents/config.yml.
            session_id: Session ID for persisting newly produced messages.
        """
        config = {"configurable": {"thread_id": thread_id}}

        # Capture step_results count before resume to slice only new ones.
        state_before = await asyncio.to_thread(self._graph.get_state, config)
        prev_count = len(state_before.values.get("step_results", []))

        result = await asyncio.to_thread(
            self._graph.invoke, Command(resume=resume_data), config=config
        )

        step_results = result.get("step_results", [])
        new_step_results = step_results[prev_count:]
        if session_id and new_step_results:
            msgs = [self._step_to_message(s) for s in new_step_results]
            context_manager.save_agent_messages(session_id, msgs)

        # Only return newly produced steps — prior steps were already sent
        # to the frontend during streaming or the initial invoke.
        content = "\n".join(s["content"] for s in new_step_results) if new_step_results else "工作流已恢复"
        return AgentResult(content=content, session_id=session_id)

    async def resume_stream(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Resume the workflow after an interrupt with streaming output.

        Mirrors stream() but starts from Command(resume=...) so the graph
        continues from the interrupt point.
        """
        config = {"configurable": {"thread_id": thread_id}}

        # Capture step_results count before resume to slice only new ones
        state_before = await asyncio.to_thread(self._graph.get_state, config)
        prev_count = len(state_before.values.get("step_results", []))

        iterator = iter(
            self._graph.stream(Command(resume=resume_data), config=config)
        )

        new_step_items = []
        while True:
            step = await asyncio.to_thread(next, iterator, _SENTINEL)
            if step is _SENTINEL:
                break
            for node_output in step.values():
                if isinstance(node_output, dict) and node_output.get("step_results"):
                    new_step_items.append(node_output["step_results"][-1])
            yield step

        # Persist new step results as messages
        if new_step_items:
            msgs = [self._step_to_message(s) for s in new_step_items]
            context_manager.save_agent_messages(session_id, msgs)

        # Check if interrupted again (chained confirmation)
        interrupt_value = await asyncio.to_thread(self._get_interrupt_value, config)
        if interrupt_value is not None:
            yield AgentResult(
                content=self._get_interrupt_message(interrupt_value),
                session_id=session_id,
                confirmation=self._build_confirmation(session_id, thread_id),
            )
