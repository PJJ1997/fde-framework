"""Tool executor with pluggable middleware chain.

Flow:
    execute() -> before_execute chain
              -> wrap_call chain (timeout, retry, etc.)
              -> after_execute chain (reverse order)
    On error -> on_error chain

All hooks receive a single ``context`` dict carrying runtime info
(session_id, permissions, etc.) instead of separate parameters.

New logic is added via executor.add_middleware(MyMiddleware()),
no need to touch the core execution flow.
"""
from typing import Any, Awaitable, Callable, List, Optional

from langchain_core.tools import StructuredTool

from .middleware.base import ToolMiddleware
from .middleware.permission import PermissionMiddleware
from .middleware.retry import RetryMiddleware
from .middleware.timeout import TimeoutMiddleware


class ToolExecutor:
    """Execute tools with a pluggable middleware chain.

    Middleware hooks and their order:
        1. before_execute — all middlewares, registration order
        2. wrap_call      — all middlewares, first-added = outermost
        3. after_execute  — all middlewares, reverse registration order
        4. on_error       — all middlewares, only if wrap_call raises

    Usage:
        executor.add_middleware(RetryMiddleware())
        executor.add_middleware(TimeoutMiddleware())
    """

    def __init__(self):
        self._middlewares: List[ToolMiddleware] = []

    def add_middleware(self, middleware: ToolMiddleware) -> None:
        """Register a middleware."""
        self._middlewares.append(middleware)

    async def execute(
        self,
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> Any:
        """Execute a tool through the middleware chain.

        Args:
            tool: The tool to execute.
            args: The arguments passed to the tool.
            context: Runtime context dict (session_id, permissions, etc.).
        """
        # before_execute chain (registration order)
        for mw in self._middlewares:
            await mw.before_execute(tool, args, context=context)

        # Call tool through wrap_call chain, then on_error if it raises.
        result = await self._call_tool(tool, args, context)

        # after_execute chain (reverse order)
        for mw in reversed(self._middlewares):
            await mw.after_execute(tool, args, result, context=context)

        return result

    async def _call_tool(
        self,
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> Any:
        """Call the tool through the wrap_call middleware chain.

        Builds a composed callable: first-added middleware is outermost.
        Example with Retry then Timeout:
            Retry.wrap_call → Timeout.wrap_call → actual tool
        Each retry attempt is individually timed.
        """
        # Innermost: the actual tool invocation
        async def _invoke():
            if tool.coroutine:
                return await tool.coroutine(**args)
            return tool.func(**args)

        # Compose wrap_call chain: iterate in reverse so first-added
        # ends up as the outermost wrapper.
        call: Callable[[], Awaitable] = _invoke
        for mw in reversed(self._middlewares):
            call = lambda c=call, mw=mw: mw.wrap_call(c, tool, args, context)

        try:
            return await call()
        except Exception as e:
            last_error = e
            for mw in self._middlewares:
                try:
                    handled = await mw.on_error(tool, args, e, context=context)
                    if handled is not None:
                        return handled
                except Exception as mw_error:
                    last_error = mw_error
            raise last_error


# Module-level singleton with default middleware.
# Order: Permission (reject early) → Retry (outermost for retry) → Timeout
executor = ToolExecutor()
executor.add_middleware(PermissionMiddleware())
executor.add_middleware(RetryMiddleware(max_retries=3, base_delay=1.0))
executor.add_middleware(TimeoutMiddleware(timeout=30.0))
