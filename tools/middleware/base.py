"""Base class for tool execution middleware."""
from typing import Any, Awaitable, Callable, Optional

from langchain_core.tools import StructuredTool


class ToolMiddleware:
    """Base class for pluggable tool execution middleware.

    Hooks:
        before_execute — pre-check before tool execution (raise to block).
        wrap_call      — wrap the tool invocation (add timeout, retry, etc.).
        after_execute  — post-processing after successful execution.
        on_error       — fallback when all wrapping fails.

    All hooks receive a ``context`` dict that carries runtime info
    (session_id, permissions, etc.). Middleware reads what it needs
    from context instead of receiving separate parameters.
    """

    async def before_execute(
        self,
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> None:
        """Called before tool execution. Raise to interrupt.

        Args:
            tool: The tool about to be executed.
            args: The arguments passed to the tool.
            context: Runtime context dict (session_id, permissions, etc.).
        """
        pass

    async def wrap_call(
        self,
        call: Callable[[], Awaitable],
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> Any:
        """Wrap the tool invocation.

        Override to add cross-cutting concerns that need to wrap the
        actual tool call — timeout, retry, circuit breaker, etc.
        Call ``await call()`` to invoke the next wrapper or the tool.

        Middlewares are composed: first-added is outermost. Example with
        RetryMiddleware added before TimeoutMiddleware:
            Retry → Timeout → tool
        So each retry attempt is individually timed.

        Args:
            call: Async callable that invokes the next middleware's
                wrap_call (or the tool itself if this is the innermost).
            tool: The tool being executed.
            args: The arguments passed to the tool.
            context: Runtime context dict (session_id, permissions, etc.).

        Returns:
            The tool result.
        """
        return await call()

    async def after_execute(
        self,
        tool: StructuredTool,
        args: dict,
        result: Any,
        context: Optional[dict] = None,
    ) -> None:
        """Called after successful tool execution.

        Args:
            tool: The tool that was executed.
            args: The arguments passed to the tool.
            result: The result returned by the tool.
            context: Runtime context dict.
        """
        pass

    async def on_error(
        self,
        tool: StructuredTool,
        args: dict,
        error: Exception,
        context: Optional[dict] = None,
    ) -> Optional[Any]:
        """Called when tool execution raises an exception.

        Override to implement error handling strategies (fallback,
        logging, etc.). Return a non-None value to swallow the error
        and use that as the result. Re-raise or raise a different
        exception to propagate.

        Note: Retry logic belongs in ``wrap_call``, not here.
        """
        raise error
