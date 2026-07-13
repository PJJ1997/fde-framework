"""MCP client implementation.

Connects to MCP server, discovers tools, and executes tool calls.
Follows MCP protocol (JSON-RPC 2.0 over stdio).
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from .transports.stdio import StdioTransport
from .wrapper import MCPToolWrapper

logger = logging.getLogger(__name__)

# MCP protocol constants
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_METHODS = {
    "initialize": "initialize",
    "list_tools": "tools/list",
    "call_tool": "tools/call",
}


class MCPClient:
    """MCP client that connects to a single MCP server.

    Handles:
      - Protocol initialization handshake
      - Tool discovery (list_tools)
      - Tool execution (call_tool)

    Usage:
        client = MCPClient("filesystem", command="node", args=["server.js"])
        await client.start()
        tools = client.list_tools()
        result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
        await client.stop()
    """

    def __init__(
        self,
        server_name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """Initialize MCP client.

        Args:
            server_name: Identifier for this MCP server
            command: Command to run (e.g., "node", "python")
            args: Command arguments
            env: Environment variables
        """
        self.server_name = server_name
        self._transport = StdioTransport(command, args, env)
        self._initialized = False
        self._request_id = 0
        _pending_requests: Dict[int, asyncio.Future] = {}
        self._tools_cache: Optional[List[Dict]] = None

    async def start(self) -> None:
        """Start the MCP server and initialize protocol."""
        await self._transport.start()

        # Perform MCP handshake
        await self._initialize()

        # Start response listener
        asyncio.create_task(self._listen_responses())

        logger.info(f"MCP client '{self.server_name}' started")

    async def _initialize(self) -> None:
        """Send initialize request and complete handshake."""
        response = await self._send_request(
            MCP_METHODS["initialize"],
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fde-agent", "version": "1.0"},
            },
        )

        if "error" in response:
            raise RuntimeError(f"MCP init failed: {response['error']}")

        self._initialized = True
        logger.info(f"MCP server capabilities: {response.get('result', {}).get('capabilities', {})}")

    async def _send_request(
        self, method: str, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send JSON-RPC request and wait for response."""
        self._request_id += 1
        request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        await self._transport.send(message)

        # Wait for response (handled by _listen_responses)
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Timeout after 30 seconds
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"MCP request timeout: {method}")
            raise
        finally:
            self._pending_requests.pop(request_id, None)

    async def _listen_responses(self) -> None:
        """Background task to receive and dispatch responses."""
        while self._initialized:
            try:
                message = await self._transport.receive()

                # Handle response to a request
                if "id" in message and message["id"] in self._pending_requests:
                    future = self._pending_requests[message["id"]]
                    if not future.done():
                        future.set_result(message)

                # Handle notifications (e.g., tools/list_changed)
                elif "method" in message and message["method"] == "notifications/tools/list_changed":
                    logger.info(f"MCP tools changed, clearing cache")
                    self._tools_cache = None

            except RuntimeError as e:
                logger.error(f"MCP listener error: {e}")
                break
            except Exception as e:
                logger.error(f"MCP listener unexpected error: {e}")

    async def stop(self) -> None:
        """Stop the MCP server."""
        self._initialized = False
        await self._transport.stop()
        logger.info(f"MCP client '{self.server_name}' stopped")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Discover available tools from MCP server.

        Returns:
            List of tool definitions with name, description, inputSchema
        """
        if self._tools_cache:
            return self._tools_cache

        response = await self._send_request(MCP_METHODS["list_tools"])

        if "error" in response:
            raise RuntimeError(f"list_tools failed: {response['error']}")

        tools = response.get("result", {}).get("tools", [])
        self._tools_cache = tools

        logger.info(f"MCP server '{self.server_name}' has {len(tools)} tools")
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool call on MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        response = await self._send_request(
            MCP_METHODS["call_tool"], {"name": name, "arguments": arguments}
        )

        if "error" in response:
            error_msg = response["error"].get("message", "Unknown error")
            raise RuntimeError(f"MCP tool '{name}' failed: {error_msg}")

        result = response.get("result", {})
        # MCP returns content array (text/image/resource)
        content = result.get("content", [])

        # Extract text content
        text_results = []
        for item in content:
            if item.get("type") == "text":
                text_results.append(item.get("text", ""))

        return "\n".join(text_results) if text_results else result

    def wrap_tools(self, permissions: Optional[Dict[str, str]] = None) -> List[MCPToolWrapper]:
        """Wrap discovered tools as StructuredTools.

        Args:
            permissions: Optional dict mapping tool names to permission strings

        Returns:
            List of MCPToolWrapper instances
        """
        # Ensure tools are loaded (sync wrapper for async method)
        if not self._tools_cache:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already async, tools will be loaded on first call
                    return []
                loop.run_until_complete(self.list_tools())
            except RuntimeError:
                asyncio.run(self.list_tools())

        wrapped = []
        for tool_def in self._tools_cache or []:
            perm = (permissions or {}).get(tool_def["name"])
            wrapped.append(MCPToolWrapper(tool_def, self, permission=perm))

        return wrapped


class MCPManager:
    """Manages multiple MCP server connections.

    Usage:
        manager = MCPManager.from_config("mcp_servers.yml")
        await manager.start_all()

        for client in manager.clients.values():
            tools.extend(client.wrap_tools())

        await manager.stop_all()
    """

    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}

    @classmethod
    def from_config(cls, config_path: str) -> "MCPManager":
        """Load MCP servers from config file."""
        from .config import load_mcp_config

        config = load_mcp_config(config_path)
        manager = cls()

        for server in config.servers:
            client = MCPClient(
                server_name=server.name,
                command=server.command,
                args=server.args,
                env=server.env,
            )
            manager.clients[server.name] = client

        return manager

    async def start_all(self) -> None:
        """Start all MCP server connections."""
        for client in self.clients.values():
            await client.start()

    async def stop_all(self) -> None:
        """Stop all MCP server connections."""
        for client in self.clients.values():
            await client.stop()

    def get_tools(self, permissions: Optional[Dict[str, Dict[str, str]]] = None) -> List[MCPToolWrapper]:
        """Get all wrapped tools from all servers.

        Args:
            permissions: Dict mapping server_name → {tool_name → permission}

        Returns:
            List of all wrapped tools
        """
        all_tools = []
        for server_name, client in self.clients.items():
            perms = (permissions or {}).get(server_name, {})
            all_tools.extend(client.wrap_tools(perms))
        return all_tools