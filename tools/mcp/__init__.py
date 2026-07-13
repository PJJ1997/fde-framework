"""MCP (Model Context Protocol) integration.

Provides transparent MCP tool integration that wraps MCP server tools
as LangChain StructuredTools, allowing executor and agents to use them
without knowing they come from MCP servers.

Key components:
  - MCPClient: Connects to MCP server, discovers tools, executes calls
  - MCPToolWrapper: Wraps MCP tool as StructuredTool
  - MCPManager: Manages multiple MCP server connections
"""
from .client import MCPClient, MCPManager
from .wrapper import MCPToolWrapper
from .config import MCPServerConfig, load_mcp_config

__all__ = [
    "MCPClient",
    "MCPManager",
    "MCPToolWrapper",
    "MCPServerConfig",
    "load_mcp_config",
]