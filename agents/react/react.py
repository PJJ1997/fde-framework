"""ReAct Agent using langchain create_agent with HumanInTheLoopMiddleware.

Uses a unique thread_id per invocation so that:
- New messages don't load the previous interrupted state (no chat history errors).
- Interrupts are preserved under their own thread_id for later resume.

Uses sync graph.invoke wrapped in asyncio.to_thread (interrupt() requires
Python 3.11+ for async usage; sync mode in a thread works on 3.10).
"""
import asyncio
import uuid
from pathlib import Path
from typing import Any, List, AsyncIterator, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command

from agents.base import BaseAgent, AgentInput, AgentResult
from context import context_manager
from prompts.system_prompt import build_system_prompt

# Sentinel for detecting iterator exhaustion without raising StopIteration.
_SENTINEL = object()


class ReActAgent(BaseAgent):
    """ReAct Agent using langchain create_agent.

    Uses HumanInTheLoopMiddleware to pause before tools flagged confirm=True.
    Each invocation gets a unique thread_id so interrupted states are
    preserved independently and don't block subsequent messages.
    """

    _shared_memory_saver = None

    def __init__(self, llm: BaseChatModel, tools: List[StructuredTool]):
        self.llm = llm
        self.tools = tools
        self._checkpointer = self._build_checkpointer()
        self._agent = self._build_agent()

    @classmethod
    def _build_checkpointer(cls):
        """Build a checkpointer shared across ReActAgent instances."""
        try:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver

            db_path = Path("data/react.db")
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

    def _build_agent(self):
        """Build the underlying agent with HumanInTheLoopMiddleware."""
        interrupt_on = {
            t.name: True for t in self.tools
            if t.metadata and t.metadata.get("confirm", False)
        }
        return create_agent(
            model=self.llm,
            tools=self.tools,
            middleware=[HumanInTheLoopMiddleware(interrupt_on=interrupt_on)],
            checkpointer=self._checkpointer,
        )

    def _get_interrupt_value(self, config: dict) -> Optional[dict]:
        """Extract the interrupt value from the agent state if interrupted."""
        state = self._agent.get_state(config)
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

    async def invoke(self, input: AgentInput) -> AgentResult:
        """Invoke the agent.

        Each invocation uses a unique thread_id so it starts fresh — no
        previous interrupted state is loaded. If HITL interrupts, the
        thread_id is returned in the confirmation for later resume.
        """
        session_id = input.session_id or str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # Build context from context_manager
        system_prompt = build_system_prompt(self.tools)
        messages = context_manager.build(
            session_id=session_id,
            system_prompt=system_prompt,
            user_input=input.user_input,
            include_history=True
        )

        result = await asyncio.to_thread(
            self._agent.invoke, {"messages": messages}, config=config
        )

        # Persist messages produced during this execution. Slice off the
        # input messages to avoid duplicating already-stored history.
        all_messages = result.get("messages", [])
        new_messages = all_messages[len(messages):]
        if new_messages:
            context_manager.save_agent_messages(session_id, new_messages)

        # Check if interrupted (HITL pause)
        interrupt_value = await asyncio.to_thread(
            self._get_interrupt_value, config
        )
        if interrupt_value is not None:
            return AgentResult(
                content="需要确认是否执行该操作",
                session_id=session_id,
                confirmation=self._build_confirmation(session_id, thread_id),
            )

        content = all_messages[-1].content if all_messages else ""
        return AgentResult(content=content, session_id=session_id)

    async def stream(self, input: AgentInput) -> AsyncIterator[Any]:
        """Stream the agent execution.

        Each invocation uses a unique thread_id so it starts fresh.
        """
        session_id = input.session_id or str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # Build context from context_manager
        system_prompt = build_system_prompt(self.tools)
        messages = context_manager.build(
            session_id=session_id,
            system_prompt=system_prompt,
            user_input=input.user_input,
            include_history=True
        )

        iterator = iter(self._agent.stream({"messages": messages}, config=config))

        new_messages = []
        while True:
            step = await asyncio.to_thread(next, iterator, _SENTINEL)
            if step is _SENTINEL:
                break
            # Collect new messages produced by this step for persistence
            for node_output in step.values():
                if isinstance(node_output, dict) and "messages" in node_output:
                    new_messages.extend(node_output["messages"])
            yield step

        # Persist messages produced during this execution
        if new_messages:
            context_manager.save_agent_messages(session_id, new_messages)

        # Check if interrupted (HITL pause)
        interrupt_value = await asyncio.to_thread(
            self._get_interrupt_value, config
        )
        if interrupt_value is not None:
            yield AgentResult(
                content="需要确认是否执行该操作",
                session_id=session_id,
                confirmation=self._build_confirmation(session_id, thread_id),
            )

    async def resume(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Resume the agent after a HITL interrupt.

        Args:
            thread_id: The thread_id from the confirmation response, pointing
                to the specific interrupted execution.
            resume_data: HITL decision format from config.yml.
            session_id: Session ID for persisting newly produced messages.
        """
        config = {"configurable": {"thread_id": thread_id}}

        # Capture message count before resume so we only persist new ones
        # (the checkpointer state already holds the pre-interrupt messages).
        state_before = await asyncio.to_thread(self._agent.get_state, config)
        prev_count = len(state_before.values.get("messages", []))

        result = await asyncio.to_thread(
            self._agent.invoke,
            Command(resume=resume_data),
            config=config,
        )

        all_messages = result.get("messages", [])
        new_messages = all_messages[prev_count:]
        if session_id:
            # The resume call itself is a user action (confirm/reject);
            # persist as a user message AFTER any leading ToolMessages.
            # OpenAI requires AIMessage(tool_calls) → ToolMessage ordering;
            # inserting HumanMessage before ToolMessage would break this.
            decisions = (
                resume_data.get("decisions", [])
                if isinstance(resume_data, dict) else []
            )
            if decisions and decisions[0].get("type") == "reject":
                action_text = "拒绝执行"
            else:
                action_text = "确认执行"
            user_msg = HumanMessage(content=action_text)
            # Find where ToolMessages end and insert HumanMessage after
            split = 0
            for i, msg in enumerate(new_messages):
                if isinstance(msg, ToolMessage):
                    split = i + 1
                else:
                    break
            context_manager.save_agent_messages(
                session_id, new_messages[:split] + [user_msg] + new_messages[split:]
            )

        content = all_messages[-1].content if all_messages else ""
        return AgentResult(content=content, session_id=session_id)

    async def resume_stream(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Resume the agent after a HITL interrupt with streaming output.

        Mirrors stream() but starts from Command(resume=...) so the agent
        continues from where it was interrupted.
        """
        config = {"configurable": {"thread_id": thread_id}}

        # Capture message count before resume so we only persist new ones
        state_before = await asyncio.to_thread(self._agent.get_state, config)
        prev_count = len(state_before.values.get("messages", []))

        iterator = iter(
            self._agent.stream(Command(resume=resume_data), config=config)
        )

        # Collect new messages from stream, but skip messages that were
        # already in the checkpointer state before resume. LangGraph may
        # replay the pre-interrupt AIMessage in the stream output, which
        # would cause duplicates in the persisted history.
        seen_ids = {
            msg.id for msg in state_before.values.get("messages", [])
            if hasattr(msg, "id") and msg.id
        }
        new_messages = []
        while True:
            step = await asyncio.to_thread(next, iterator, _SENTINEL)
            if step is _SENTINEL:
                break
            for node_output in step.values():
                if isinstance(node_output, dict) and "messages" in node_output:
                    for msg in node_output["messages"]:
                        # Skip messages already in pre-resume state
                        if hasattr(msg, "id") and msg.id and msg.id in seen_ids:
                            continue
                        new_messages.append(msg)
            yield step

        # Persist the user's confirmation + agent's new messages
        if session_id:
            decisions = (
                resume_data.get("decisions", [])
                if isinstance(resume_data, dict) else []
            )
            if decisions and decisions[0].get("type") == "reject":
                action_text = "拒绝执行"
            else:
                action_text = "确认执行"
            user_msg = HumanMessage(content=action_text)
            # Insert HumanMessage after leading ToolMessages
            split = 0
            for i, msg in enumerate(new_messages):
                if isinstance(msg, ToolMessage):
                    split = i + 1
                else:
                    break
            context_manager.save_agent_messages(
                session_id, new_messages[:split] + [user_msg] + new_messages[split:]
            )

        # Check if interrupted again (chained confirmation)
        interrupt_value = await asyncio.to_thread(
            self._get_interrupt_value, config
        )
        if interrupt_value is not None:
            yield AgentResult(
                content="需要确认是否执行该操作",
                session_id=session_id,
                confirmation=self._build_confirmation(session_id, thread_id),
            )
