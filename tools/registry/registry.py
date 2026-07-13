"""Simple tool registry."""
import asyncio
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

from langchain_core.tools import StructuredTool

from ..executor import executor as _executor, ToolExecutor

if TYPE_CHECKING:
    from ..mcp import MCPClient, MCPManager, MCPToolWrapper

logger = logging.getLogger(__name__)


def wrap_tool_with_executor(
    tool: StructuredTool,
    executor: ToolExecutor,
    context: Optional[dict] = None,
) -> StructuredTool:
    """Wrap a tool so that it goes through ToolExecutor.execute().

    All tools are wrapped so that the middleware chain always runs.
    Any exception from the middleware chain (permission denied,
    timeout, retry exhausted, etc.) is caught and returned as an
    error dict. This ensures LangGraph always produces a ToolMessage
    for every tool_call — OpenAI requires the message chain to be
    complete or it rejects subsequent requests.

    Args:
        tool: The StructuredTool to wrap.
        executor: ToolExecutor instance.
        context: Runtime context dict (session_id, permissions, etc.).
    """
    original_tool = tool

    async def wrapped_coroutine(**kwargs):
        try:
            return await executor.execute(original_tool, kwargs, context=context)
        except Exception as e:
            # Catch ALL exceptions so LangGraph always produces a
            # ToolMessage. Without this, any middleware error breaks
            # the message chain (OpenAI requires every tool_call to
            # have a corresponding ToolMessage).
            print(f"[ToolWrapper] {original_tool.name} failed: {type(e).__name__}: {e}")
            return {"error": str(e)}

    def wrapped_func(**kwargs):
        return asyncio.run(wrapped_coroutine(**kwargs))

    return StructuredTool.from_function(
        func=wrapped_func,
        coroutine=wrapped_coroutine,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        metadata=tool.metadata,
    )


class ToolRegistry:
    """Simple registry for LangChain StructuredTool instances."""

    def __init__(self):
        self._tools: Dict[str, StructuredTool] = {}
        self._executor = _executor

    def register(
        self,
        tool: StructuredTool,
        confirm: bool = False,
        permission: Optional[str] = None,
    ) -> None:
        """Register a LangChain StructuredTool.

        Args:
            tool: StructuredTool instance to register
            confirm: If True, the tool requires user confirmation before execution
            permission: Required permission string (e.g. "erp.order.write").
                Format: [system].[resource].[action]. If None, no permission
                is required (backward compatible).
        """
        metadata = dict(tool.metadata or {})
        metadata["confirm"] = confirm
        if permission:
            metadata["permission"] = permission
        tool.metadata = metadata
        self._tools[tool.name] = tool

    def get_tools(
        self,
        context: Optional[dict] = None,
        tool_names: Optional[List[str]] = None,
    ) -> List[StructuredTool]:
        """Get tools, optionally wrapped with executor.

        Args:
            context: If provided, tools are wrapped with ToolExecutor
                (middleware chain) and context is passed through.
                If None, raw tools are returned.
            tool_names: Optional list of tool names. If None, returns all.

        Returns:
            List of StructuredTool instances (wrapped or raw).
        """
        if tool_names is None:
            tools = list(self._tools.values())
        else:
            tools = [self._tools[name] for name in tool_names if name in self._tools]

        if context is not None:
            tools = [
                wrap_tool_with_executor(t, self._executor, context=context)
                for t in tools
            ]

        return tools

    def register_from_mcp(
        self,
        mcp_client: "MCPClient",
        permissions: Optional[Dict[str, str]] = None,
    ) -> int:
        """Register tools from an MCP server.

        Tools are discovered via MCP list_tools and wrapped as StructuredTools.
        Permissions from config are applied to each tool.

        Args:
            mcp_client: MCPClient instance (must be started)
            permissions: Dict mapping tool_name → permission string

        Returns:
            Number of tools registered
        """
        try:
            wrapped_tools = mcp_client.wrap_tools(permissions)
            for tool in wrapped_tools:
                # MCPToolWrapper already has permission in metadata
                self._tools[tool.name] = tool
                logger.info(f"Registered MCP tool: {tool.name} from '{mcp_client.server_name}'")
            return len(wrapped_tools)
        except Exception as e:
            logger.error(f"Failed to register MCP tools from '{mcp_client.server_name}': {e}")
            return 0

    def register_from_mcp_manager(
        self,
        mcp_manager: "MCPManager",
        permissions: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> int:
        """Register tools from all MCP servers managed by MCPManager.

        Args:
            mcp_manager: MCPManager instance (must be started)
            permissions: Dict mapping server_name → {tool_name → permission}

        Returns:
            Total number of tools registered
        """
        total = 0
        for server_name, client in mcp_manager.clients.items():
            perms = (permissions or {}).get(server_name, {})
            total += self.register_from_mcp(client, perms)
        return total


# Global registry instance
registry = ToolRegistry()
