"""Retry middleware - retries tool calls on non-business errors.

Only retries on infrastructure-level errors (network failures, server
errors like 500, timeouts, etc.). Business errors (e.g. "order not
found", validation failures) are not retried because the result won't
change.

By default, retries up to 3 times with exponential backoff (1s, 2s, 4s).
Uses wrap_call so the retry loop is fully owned by this middleware —
the executor has no retry logic.
"""
import asyncio
from typing import Any, Awaitable, Callable, Optional, Set, Type

from langchain_core.tools import StructuredTool

from .base import ToolMiddleware


# Common infrastructure exception types that indicate transient errors.
_DEFAULT_RETRYABLE_ERRORS: Set[Type[Exception]] = {
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionAbortedError,
    TimeoutError,
    OSError,
}


class RetryMiddleware(ToolMiddleware):
    """Retries tool calls on transient infrastructure errors.

    Inspects the exception type to decide whether an error is retryable
    (infrastructure) or not (business logic). Only retryable errors
    trigger a retry.

    Uses ``wrap_call`` to own the retry loop — the executor just calls
    wrap_call and gets back a result or an exception.

    Args:
        max_retries: Maximum number of retries (default 3, so up to 4
            total attempts including the initial one).
        base_delay: Base delay in seconds for exponential backoff.
        retryable_errors: Set of exception types considered retryable.
            Defaults to connection/timeout/OS errors. Add custom types
            as needed.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        retryable_errors: Optional[Set[Type[Exception]]] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.retryable_errors = retryable_errors or _DEFAULT_RETRYABLE_ERRORS

    def _is_retryable(self, error: Exception) -> bool:
        """Check if an error is retryable (infrastructure, not business)."""
        if type(error) in self.retryable_errors:
            return True
        for err_type in self.retryable_errors:
            if isinstance(error, err_type):
                return True
        # Duck typing: many HTTP clients raise errors with status_code.
        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            return 500 <= int(status_code) < 600
        return False

    async def wrap_call(
        self,
        call: Callable[[], Awaitable],
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> Any:
        """Wrap the tool call with retry logic on transient errors."""
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return await call()
            except Exception as e:
                last_error = e
                if not self._is_retryable(e) or attempt == self.max_retries:
                    raise
                delay = self.base_delay * (2 ** attempt)
                print(
                    f"[RetryMiddleware] {tool.name} attempt {attempt + 1} "
                    f"failed ({type(e).__name__}: {e}), "
                    f"retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        # Should not reach here, but just in case.
        raise last_error  # type: ignore[misc]
