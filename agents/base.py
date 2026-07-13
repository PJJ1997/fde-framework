"""Base agent abstract class."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional, AsyncIterator

from langchain_core.messages import BaseMessage


@dataclass
class AgentInput:
    """Unified input for agent execution.

    Attributes:
        messages: List of LangChain message objects.
        session_id: Session ID for context tracking and middleware.
        state: Optional agent-specific state dict. Workflow agents use it to
            pass business params (e.g. order fields) without forcing every
            agent to know workflow-specific fields. Other agents ignore it.
    """

    messages: List[BaseMessage] = field(default_factory=list)
    session_id: Optional[str] = None
    state: Optional[dict] = None


@dataclass
class AgentResult:
    """Unified result from agent execution.

    Attributes:
        content: Text content from the agent or tool.
        confirmation: If a middleware interrupted execution (e.g. a tool
            needs user confirmation), this holds the confirmation dict.
            None when execution completed normally.
        session_id: Session ID for context tracking.
    """

    content: str = ""
    confirmation: Optional[dict] = None
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict for API responses."""
        return {
            "content": self.content,
            "confirmation": self.confirmation,
            "session_id": self.session_id,
        }


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    @abstractmethod
    async def invoke(self, input: AgentInput) -> AgentResult:
        """Invoke the agent.

        Args:
            input: AgentInput with messages and session_id.

        Returns:
            AgentResult with content, confirmation, and session_id.
        """
        pass

    @abstractmethod
    async def stream(self, input: AgentInput) -> AsyncIterator[Any]:
        """Stream the agent execution.

        Args:
            input: AgentInput with messages and session_id.

        Yields:
            Agent execution steps as dictionaries, or a final AgentResult
            if execution was interrupted (e.g. confirmation needed).
        """
        pass

    @abstractmethod
    async def resume(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Resume agent execution after an interrupt.

        Args:
            thread_id: The thread_id from the confirmation response,
                identifying the specific interrupted execution in the
                checkpointer.
            resume_data: Resume format from agents/config.yml.
            session_id: Session ID for persisting newly produced messages.
                None when the caller does not need persistence.

        Returns:
            AgentResult with content, confirmation, and session_id.
        """
        pass

    @abstractmethod
    async def resume_stream(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Resume agent execution with streaming output.

        Streams step-by-step output after resuming from an interrupt,
        mirroring stream() but starting from a Command(resume=...) input.

        Args:
            thread_id: The thread_id from the confirmation response.
            resume_data: Resume format from agents/config.yml.
            session_id: Session ID for persisting newly produced messages.

        Yields:
            LangGraph step dicts, and a final AgentResult if another
            interrupt occurs (for chained confirmations).
        """
        pass
