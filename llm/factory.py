"""LLM factory."""
from typing import Optional
from langchain_core.language_models import BaseChatModel


def create_llm(provider: Optional[str] = None) -> BaseChatModel:
    """Create a LangChain LLM instance.

    Args:
        provider: LLM provider name. If None, use "deepseek".

    Returns:
        LangChain BaseChatModel instance
    """
    if provider is None:
        provider = "deepseek"

    if provider == "deepseek":
        from .providers.deepseek import create_deepseek_llm
        return create_deepseek_llm()
    else:
        raise ValueError(f"Unknown provider: {provider}")