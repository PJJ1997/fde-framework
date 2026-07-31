"""Environment-backed configuration helpers for LLM integrations."""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_environment(env_path: Optional[Path] = None) -> None:
    """Load local configuration without overriding process variables."""
    load_dotenv(
        dotenv_path=env_path or DEFAULT_ENV_PATH,
        override=False,
    )


def get_env(
    name: str,
    default: Optional[str] = None,
    required: bool = False,
) -> str:
    """Read and normalize an environment variable."""
    value = os.getenv(name, default)
    normalized = value.strip() if value is not None else ""
    if required and not normalized:
        raise ValueError(f"Required environment variable is missing: {name}")
    return normalized


def get_float_env(name: str, default: float) -> float:
    """Read an environment variable as a float."""
    value = get_env(name, str(default))
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(
            f"Environment variable {name} must be a number"
        ) from error
