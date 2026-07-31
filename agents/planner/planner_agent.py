"""Planner-Executor-Reviewer-Responder Agent using LangGraph.

Implements a three-stage agent architecture:
1. Planner: Generates structured execution plan
2. Executor: Executes all steps in the plan sequentially
3. Reviewer: Evaluates results and decides PASS/REPLAN/FAIL
4. Responder: Turns reviewed results into the final user response

Flow:
START -> Context Builder -> Planner -> Executor -> Reviewer
                              ↑                    |
                              └──── REPLAN ────────┘
                                   PASS/FAIL -> Responder -> END
"""
import asyncio
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from agents.base import BaseAgent, AgentInput, AgentResult
from context import context_manager
from tools.registry import registry
from .nodes import (
    ContextBuilderNode,
    ExecutorNode,
    PlannerNode,
    ReviewerNode,
    ResponderNode,
    route_after_planner,
    route_after_reviewer,
)
from .schemas import PlannerState, ReviewDecision


class PlannerAgent(BaseAgent):
    """Planner-Executor-Reviewer Agent.
    
    Structured multi-agent workflow:
    - Planner generates execution plans using LLM
    - Executor runs all steps sequentially via tools
    - Reviewer evaluates and decides next action
    
    Supports automatic replanning on failure.
    """

    _shared_memory_saver = None

    def __init__(self, llm: BaseChatModel, max_iterations: int = 3):
        self.llm = llm
        self.max_iterations = max_iterations
        self._checkpointer = self._build_checkpointer()
        self._tools = {t.name: t for t in registry.get_tools()}
        self._graph = self._build_graph()

    @classmethod
    def _build_checkpointer(cls):
        """Build checkpointer for state persistence."""
        try:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver

            db_path = Path("data/planner.db")
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
        """Build the Planner-Executor-Reviewer graph."""
        # Create node instances
        context_builder_node = ContextBuilderNode(self.llm)
        planner_node = PlannerNode(self.llm, self._tools)
        executor_node = ExecutorNode(self._tools)
        reviewer_node = ReviewerNode(self.llm)
        responder_node = ResponderNode(self.llm)

        graph = StateGraph(PlannerState)
        graph.add_node("context_builder", context_builder_node)
        graph.add_node("planner", planner_node)
        graph.add_node("executor", executor_node)
        graph.add_node("reviewer", reviewer_node)
        graph.add_node("responder", responder_node)

        # Edges
        graph.add_edge(START, "context_builder")
        graph.add_edge("context_builder", "planner")

        # Conditional edge from planner: execute → executor, need_input/reject → END
        graph.add_conditional_edges(
            "planner",
            route_after_planner,
            {
                "executor": "executor",  # decision=execute
                "end": END,               # decision=need_input or reject
            },
        )

        graph.add_edge("executor", "reviewer")

        # Conditional edge from reviewer
        graph.add_conditional_edges(
            "reviewer",
            route_after_reviewer,
            {
                "planner": "planner",  # REPLAN
                "responder": "responder",  # PASS or FAIL
            },
        )
        graph.add_edge("responder", END)

        return graph.compile(checkpointer=self._checkpointer)

    def _build_initial_state(self, input: AgentInput) -> dict:
        """Build initial planner state from AgentInput."""
        session_id = input.session_id or str(uuid.uuid4())

        # Extract user goal from the last message
        user_goal = ""
        if input.messages:
            last_human = None
            for msg in reversed(input.messages):
                if isinstance(msg, HumanMessage):
                    last_human = msg
                    break
            if last_human:
                user_goal = last_human.content

        return {
            "session_id": session_id,
            "messages": input.messages,  # Pass all messages for context
            "user_goal": user_goal,
            "structured_context": None,
            "planner_decision": None,
            "planner_result": None,
            "plan_json": None,
            "step_results": [],
            "review_decision": None,
            "review_feedback": None,
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "final_content": None,
        }

    async def invoke(self, input: AgentInput) -> AgentResult:
        """Invoke the planner agent."""
        initial_state = self._build_initial_state(input)
        session_id = initial_state["session_id"]
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        result = await asyncio.to_thread(
            self._graph.invoke, initial_state, config=config
        )

        # Get final content
        content = result.get("final_content", "")
        if not content:
            content = "执行完成"
        
        # Save to context
        context_manager.save_agent_messages(
            session_id,
            [AIMessage(content=content)]
        )

        return AgentResult(content=content, session_id=session_id)

    async def stream(self, input: AgentInput) -> AsyncIterator[Any]:
        """Stream planner agent execution."""
        initial_state = self._build_initial_state(input)
        session_id = initial_state["session_id"]
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        iterator = iter(self._graph.stream(initial_state, config=config))

        final_content = None
        while True:
            step = await asyncio.to_thread(next, iterator, None)
            if step is None:
                break

            # Don't yield intermediate steps - only extract final_content
            for node_output in step.values():
                if isinstance(node_output, dict):
                    final_content = node_output.get("final_content") or final_content

        # Yield only the final result
        if final_content:
            context_manager.save_agent_messages(
                session_id,
                [AIMessage(content=final_content)]
            )
            yield AgentResult(content=final_content, session_id=session_id)

    async def resume(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Resume not supported for PlannerAgent (no interrupts)."""
        return AgentResult(
            content="PlannerAgent does not support resume (no interrupts)",
            session_id=session_id,
        )

    async def resume_stream(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Resume stream not supported for PlannerAgent (no interrupts)."""
        yield AgentResult(
            content="PlannerAgent does not support resume_stream (no interrupts)",
            session_id=session_id,
        )
