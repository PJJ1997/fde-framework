"""Azure OpenAI embeddings provider.

Uses Azure OpenAI's text-embedding models for high-quality semantic embeddings.
Supports text-embedding-ada-002, text-embedding-3-small, and text-embedding-3-large.
"""
from typing import Optional

from langchain_openai import AzureOpenAIEmbeddings
from langchain_core.embeddings import Embeddings

from llm.config import get_env, load_environment


def create_azure_openai_embeddings(
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
) -> Embeddings:
    """Create Azure OpenAI embeddings instance.
    
    Args:
        model: Embedding model deployment name. If None, reads from
            AZURE_OPENAI_EMBEDDING_DEPLOYMENT environment variable.
            Common choices:
            - text-embedding-ada-002 (1536 dimensions, legacy)
            - text-embedding-3-small (512 or 1536 dimensions)
            - text-embedding-3-large (256, 1024, or 3072 dimensions)
        dimensions: Optional output dimension for text-embedding-3 models.
            Allows you to reduce embedding size for faster search.
            Must be specified for text-embedding-3 models if you want
            non-default dimensions.
    
    Returns:
        Embeddings instance configured for Azure OpenAI.
    
    Environment Variables:
        AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint URL (required)
        AZURE_OPENAI_API_KEY: Azure OpenAI API key (required)
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT: Embedding model deployment name (required if model not provided)
        AZURE_OPENAI_API_VERSION: API version (optional, defaults to "2025-04-01-preview")
    
    Example:
        >>> # Use default configuration from .env
        >>> embeddings = create_azure_openai_embeddings()
        
        >>> # Use specific model with custom dimensions
        >>> embeddings = create_azure_openai_embeddings(
        ...     model="text-embedding-3-large",
        ...     dimensions=1024
        ... )
        
        >>> # Embed documents
        >>> vectors = embeddings.embed_documents(["Hello world", "RAG is awesome"])
        
        >>> # Embed query
        >>> query_vector = embeddings.embed_query("What is RAG?")
    """
    load_environment()
    
    # Get deployment name from parameter or environment
    deployment = model or get_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", required=True)
    
    # Build kwargs for AzureOpenAIEmbeddings
    kwargs = {
        "azure_deployment": deployment,
        "azure_endpoint": get_env("AZURE_OPENAI_ENDPOINT", required=True),
        "api_key": get_env("AZURE_OPENAI_API_KEY", required=True),
        "api_version": get_env("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    }
    
    # Add dimensions if specified (only for text-embedding-3 models)
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    
    return AzureOpenAIEmbeddings(**kwargs)


def create_embeddings(model: Optional[str] = None) -> Embeddings:
    """Create embeddings instance - alias for compatibility.
    
    This function maintains compatibility with the local.py interface
    while providing Azure OpenAI embeddings.
    
    Args:
        model: Embedding model deployment name. If None, reads from environment.
    
    Returns:
        Embeddings instance.
    """
    return create_azure_openai_embeddings(model=model)
