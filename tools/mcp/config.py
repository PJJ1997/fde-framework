"""MCP server configuration loading."""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server.

    Attributes:
        name: Server identifier
        command: Executable command (e.g., "node", "python")
        args: Command arguments
        env: Environment variables
        transport: Transport type ("stdio", "sse", "websocket")
        permissions: Tool-specific permissions {tool_name: permission}
    """

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"
    permissions: Dict[str, str] = field(default_factory=dict)


@dataclass
class MCPConfig:
    """Root MCP configuration.

    Attributes:
        servers: List of MCP server configurations
    """

    servers: List[MCPServerConfig] = field(default_factory=list)


def load_mcp_config(config_path: str) -> MCPConfig:
    """Load MCP server configuration from YAML file.

    Args:
        config_path: Path to mcp_servers.yml

    Returns:
        MCPConfig instance
    """
    if not os.path.exists(config_path):
        return MCPConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    servers = []
    for server_data in data.get("mcp_servers", []):
        server = MCPServerConfig(
            name=server_data.get("name", "unknown"),
            command=server_data.get("command", ""),
            args=server_data.get("args", []),
            env=server_data.get("env", {}),
            transport=server_data.get("transport", "stdio"),
            permissions=server_data.get("permissions", {}),
        )
        servers.append(server)

    return MCPConfig(servers=servers)