"""LangSmith tracing setup.

Loads tracing configuration from .env. LangChain/LangGraph automatically
send traces to LangSmith when these env vars are set:
  - LANGSMITH_TRACING=true       enable tracing
  - LANGSMITH_API_KEY=<key>      authentication
  - LANGSMITH_PROJECT=<name>     trace grouping (optional, defaults below)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Default project name if not set in .env.
_DEFAULT_PROJECT = "fde-framework"


def setup_tracing() -> None:
    """Load .env and enable LangSmith tracing.

    Must be called before any LangChain import so the env vars are visible
    when LangChain initializes its tracing client.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

    if not os.getenv("LANGSMITH_API_KEY"):
        print("[Tracing] LANGSMITH_API_KEY missing, tracing disabled")
        return

    if os.getenv("LANGSMITH_PROJECT") is None:
        os.environ["LANGSMITH_PROJECT"] = _DEFAULT_PROJECT

    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        print(
            f"[Tracing] LangSmith enabled, "
            f"project={os.getenv('LANGSMITH_PROJECT')}"
        )
    else:
        print("[Tracing] LangSmith disabled (LANGSMITH_TRACING != true)")
