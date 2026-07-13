"""Timeout middleware - enforces a time limit on tool calls.

Uses asyncio.wait_for to cancel tool execution if it exceeds the
configured timeout. Raises asyncio.TimeoutError (which IS a subclass
of the built-in TimeoutError) so RetryMiddleware can catch and retry
if needed.

Composition order matters:
    executor.add_middleware(RetryMiddleware())   # outermost
    executor.add_middleware(TimeoutMiddleware())  # innermost

Result: Retry → Timeout → tool. Each retry attempt is individually
timed. If Timeout is outermost instead, the entire retry sequence
would share one timeout.
"""
import asyncio
from typing import Any, Awaitable, Callable, Optional

from langchain_core.tools import StructuredTool

from .base import ToolMiddleware


class TimeoutMiddleware(ToolMiddleware):
    """Enforce a time limit on tool execution.

    Wraps the tool call with ``asyncio.wait_for``. If the call exceeds
    the timeout, it is cancelled and ``asyncio.TimeoutError`` is raised.

    Args:
        timeout: Maximum seconds a tool call is allowed to run.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def wrap_call(
        self,
        call: Callable[[], Awaitable],
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> Any:
        """Wrap the tool call with a timeout."""
        try:
            return await asyncio.wait_for(call(), timeout=self.timeout)
        except asyncio.TimeoutError:
            print(
                f"[TimeoutMiddleware] {tool.name} timed out "
                f"after {self.timeout}s"
            )
            raise
