"""MCP tool wrapper that implements StructuredTool interface.

Allows executor and agents to use MCP tools without knowing they come
from MCP servers. The wrapper transparently forwards calls to MCP client.
"""
import asyncio
import logging
from typing import Any, Dict, Optional, Type

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

logger = logging.getLogger(__name__)


def _schema_to_pydantic(input_schema: Dict[str, Any]) -> Type[BaseModel]:
    """Convert MCP inputSchema to Pydantic model.

    Args:
        input_schema: MCP tool input schema (JSON Schema format)

    Returns:
        Pydantic model class for validation
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    fields = {}
    for name, prop in properties.items():
        # Map JSON Schema types to Python types
        prop_type = prop.get("type", "string")
        py_type: type = str

        if prop_type == "string":
            py_type = str
        elif prop_type == "integer":
            py_type = int
        elif prop_type == "number":
            py_type = float
        elif prop_type == "boolean":
            py_type = bool
        elif prop_type == "array":
            py_type = list
        elif prop_type == "object":
            py_type = dict

        # Handle required vs optional
        if name in required:
            fields[name] = (py_type, ...)
        else:
            default = prop.get("default", None)
            fields[name] = (py_type, default)

    # Create dynamic Pydantic model
    return create_model("MCPToolInput", **fields)


class MCPToolWrapper(StructuredTool):
    """Wraps an MCP tool as a LangChain StructuredTool.

    The executor can call this tool through its middleware chain
    without knowing it's actually an MCP server call.

    Attributes:
        tool_name: MCP tool name
        tool_def: Original MCP tool definition
        mcp_client: MCP client for executing calls
    """

    tool_name: str
    tool_def: Dict[str, Any]
    mcp_client: Any  # MCPClient reference (avoid circular import)

    def __init__(
        self,
        tool_def: Dict[str, Any],
        mcp_client: Any,
        permission: Optional[str] = None,
    ):
        """Initialize MCP tool wrapper.

        Args:
            tool_def: MCP tool definition from list_tools
            mcp_client: MCPClient instance for executing calls
            permission: Optional permission requirement (from metadata)
        """
        name = tool_def.get("name", "unknown")
        description = tool_def.get("description", "")
        input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

        # Build Pydantic args_schema from inputSchema
        args_schema = _schema_to_pydantic(input_schema)

        super().__init__(
            name=name,
            description=description,
            args_schema=args_schema,
            func=self._execute_sync,
            coroutine=self._execute_async,
        )

        # Store references for execution
        self.tool_name = name
        self.tool_def = tool_def
        self.mcp_client = mcp_client

        # Set metadata for middleware (permission, approval, etc.)
        self.metadata = {"permission": permission}

    def _execute_sync(self, **args) -> Any:
        """Sync wrapper for coroutine (used by StructuredTool.func)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, need to run in executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self._execute_async(**args))
                    return future.result()
            else:
                return loop.run_until_complete(self._execute_async(**args))
        except RuntimeError:
            # No event loop, create new one
            return asyncio.run(self._execute_async(**args))

    async def _execute_async(self, **args) -> Any:
        """Execute tool call via MCP client."""
        logger.debug(f"MCP tool call: {self.tool_name} with args={args}")
        result = await self.mcp_client.call_tool(self.tool_name, args)
        logger.debug(f"MCP tool result: {self.tool_name} → {result}")
        return result

    def __repr__(self) -> str:
        return f"MCPToolWrapper(name={self.tool_name}, server={self.mcp_client.server_name})"