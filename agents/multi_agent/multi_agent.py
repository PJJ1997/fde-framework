"""Multi-Agent using LangGraph."""
from typing import Any, List, AsyncIterator, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import StructuredTool

from agents.base import BaseAgent, AgentInput, AgentResult


class MultiAgent(BaseAgent):
    """Multi-Agent - supervisor pattern with multiple specialized agents.

    TODO: Implement multi-agent with supervisor routing.
    """

    def __init__(self, llm: BaseChatModel, tools: List[StructuredTool]):
        self.llm = llm
        self.tools = tools

    async def invoke(self, input: AgentInput) -> AgentResult:
        raise NotImplementedError("MultiAgent not yet implemented")

    async def stream(self, input: AgentInput) -> AsyncIterator[Any]:
        raise NotImplementedError("MultiAgent not yet implemented")

    async def resume(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        raise NotImplementedError("MultiAgent not yet implemented")

    async def resume_stream(
        self,
        thread_id: str,
        resume_data: dict,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        raise NotImplementedError("MultiAgent not yet implemented")
