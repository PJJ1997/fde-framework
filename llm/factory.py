"""LLM factory."""
from typing import Optional

from langchain_core.language_models import BaseChatModel

from .config import get_env, load_environment


def create_llm(provider: Optional[str] = None) -> BaseChatModel:
    """Create a LangChain LLM instance.

    Args:
        provider: LLM provider name. Options: "deepseek", "azure_openai".
                 If None, reads LLM_PROVIDER from the environment.

    Returns:
        LangChain BaseChatModel instance
    """
    load_environment()
    provider = provider or get_env("LLM_PROVIDER", "azure_openai")

    if provider == "deepseek":
        from .providers.deepseek import create_deepseek_llm
        return create_deepseek_llm()
    elif provider == "azure_openai":
        from .providers.azure_openai import create_azure_openai_llm
        return create_azure_openai_llm()
    else:
        raise ValueError(f"Unknown provider: {provider}. Available: deepseek, azure_openai")
