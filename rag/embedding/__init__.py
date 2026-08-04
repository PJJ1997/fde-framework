"""Embedding providers for RAG system.

Supports multiple embedding backends:
- local: Lightweight n-gram embeddings (no external dependencies)
- azure_openai: Azure OpenAI text-embedding models (production quality)

The factory function automatically selects the provider based on
EMBEDDING_PROVIDER environment variable.
"""
from typing import Optional

from langchain_core.embeddings import Embeddings

from llm.config import get_env, load_environment


def create_embeddings(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Embeddings:
    """Create an embeddings instance based on the provider.

    Args:
        provider: Embedding provider name. Options: "local", "azure_openai".
            If None, reads EMBEDDING_PROVIDER from environment (defaults to "local").
        model: Model name for the provider. Meaning depends on provider:
            - local: Ignored (no model needed)
            - azure_openai: Azure deployment name (e.g. "text-embedding-3-large")

    Returns:
        Embeddings instance for the specified provider.

    Environment Variables:
        EMBEDDING_PROVIDER: Provider name (default: "local")
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT: Azure embedding deployment name
            (required if provider is "azure_openai" and model not specified)

    Examples:
        >>> # Use default provider from environment
        >>> embeddings = create_embeddings()

        >>> # Explicitly use Azure OpenAI
        >>> embeddings = create_embeddings(provider="azure_openai")

        >>> # Use specific Azure model
        >>> embeddings = create_embeddings(
        ...     provider="azure_openai",
        ...     model="text-embedding-3-large"
        ... )

    Raises:
        ValueError: If provider is unknown or required configuration is missing.
    """
    load_environment()
    provider = provider or get_env("EMBEDDING_PROVIDER", "local")

    if provider == "local":
        from .local import create_embeddings as create_local
        return create_local(model=model)

    elif provider == "azure_openai":
        from .azure_openai import create_azure_openai_embeddings
        return create_azure_openai_embeddings(model=model)

    else:
        raise ValueError(
            f"Unknown embedding provider: {provider}. "
            f"Available: local, azure_openai"
        )


__all__ = ["create_embeddings"]
