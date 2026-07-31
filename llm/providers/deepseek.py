"""DeepSeek LLM provider."""
from langchain_openai import ChatOpenAI

from ..config import get_env, get_float_env, load_environment


def create_deepseek_llm() -> ChatOpenAI:
    """Create DeepSeek LLM instance.

    DeepSeek uses OpenAI-compatible API.
    """
    load_environment()
    return ChatOpenAI(
        model=get_env("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=get_env("DEEPSEEK_API_KEY", required=True),
        base_url=get_env(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        ),
        temperature=get_float_env("LLM_TEMPERATURE", 0.7),
    )
