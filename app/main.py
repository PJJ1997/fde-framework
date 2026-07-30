"""FastAPI application."""
from tracing import setup_tracing
setup_tracing()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import chat_router, actions_router

# Import tools to register them
import tools.providers
from tools.registry import registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown."""
    # Startup
    yield
    # Shutdown


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