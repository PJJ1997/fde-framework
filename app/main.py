"""FastAPI application."""
from tracing import setup_tracing
setup_tracing()

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import chat_router, actions_router

# Import tools to register them
import tools.providers
from tools.registry import registry
from tools.mcp import MCPManager


MCP_CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "mcp_servers.yml")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown."""
    # Startup: Load MCP servers
    mcp_manager = MCPManager.from_config(MCP_CONFIG_PATH)

    if mcp_manager.clients:
        await mcp_manager.start_all()
        # Register MCP tools
        count = registry.register_from_mcp_manager(mcp_manager)
        print(f"[MCP] Registered {count} tools from {len(mcp_manager.clients)} servers")
        app.state.mcp_manager = mcp_manager

    yield

    # Shutdown: Stop MCP servers
    if hasattr(app.state, "mcp_manager"):
        await app.state.mcp_manager.stop_all()
        print("[MCP] All servers stopped")


app = FastAPI(title="FDE Framework", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(actions_router)