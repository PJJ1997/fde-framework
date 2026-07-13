"""MCP stdio transport.

MCP communicates via stdin/stdout (most common transport).
No base class needed since we only support stdio.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StdioTransport:
    """Stdio-based MCP transport.

    Spawns a subprocess and communicates via stdin/stdout using JSON-RPC.
    """

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """Initialize stdio transport.

        Args:
            command: The command to run (e.g., "node", "python")
            args: Command arguments
            env: Environment variables for the subprocess
        """
        self._command = command
        self._args = args or []
        self._env = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def start(self) -> None:
        """Spawn the subprocess and initialize streams."""
        logger.info(f"Starting MCP server: {self._command} {self._args}")

        # Merge environment with current process env
        full_env = dict(os.environ)
        full_env.update(self._env)

        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )

        self._reader = self._process.stdout
        self._writer = self._process.stdin

        # Start stderr logger in background
        asyncio.create_task(self._log_stderr())

        logger.info(f"MCP server started (pid={self._process.pid})")

    async def _log_stderr(self) -> None:
        """Log stderr output from the subprocess."""
        if not self._process or not self._process.stderr:
            return
        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            logger.debug(f"[MCP stderr] {line.decode().strip()}")

    async def stop(self) -> None:
        """Terminate the subprocess."""
        if self._process:
            logger.info(f"Stopping MCP server (pid={self._process.pid})")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None
            self._reader = None
            self._writer = None

    async def send(self, message: Dict[str, Any]) -> None:
        """Send a JSON-RPC message via stdin."""
        if not self._writer:
            raise RuntimeError("Transport not started")

        content = json.dumps(message)
        # MCP protocol: newline-delimited JSON
        self._writer.write(content.encode() + b"\n")
        await self._writer.drain()
        logger.debug(f"[MCP →] {content}")

    async def receive(self) -> Dict[str, Any]:
        """Receive a JSON-RPC message from stdout."""
        if not self._reader:
            raise RuntimeError("Transport not started")

        line = await self._reader.readline()
        if not line:
            raise RuntimeError("MCP server closed connection")

        content = line.decode().strip()
        logger.debug(f"[MCP ←] {content}")
        return json.loads(content)


__all__ = ["StdioTransport"]