"""RAG domain models, enums, and exceptions.

Enterprise-grade domain models for multi-tenant RAG system with
knowledge base management, document versioning, and access control.
"""
from .enums import Category, DocumentType, KnowledgeBaseStatus
from .exceptions import (
    AccessDeniedError,
    DocumentNotFoundError,
    EmbeddingError,
    InvalidMetadataError,
    RAGError,
    UnsupportedDocumentTypeError,
    VersionConflictError,
    VectorStoreError,
)
from .models import (
    AccessContext,
    Chunk,
    Document,
    DocumentVersion,
    KnowledgeBase,
    SearchFilter,
    SearchQuery,
    SearchRequest,
    SearchResult,
    Tenant,
)

# Backward compatibility - import ChunkMetadata from schema
from ..schema import ChunkMetadata


__all__ = [
    # Enums
    "Category",
    "DocumentType",
    "KnowledgeBaseStatus",
    # Exceptions
    "RAGError",
    "DocumentNotFoundError",
    "UnsupportedDocumentTypeError",
    "VectorStoreError",
    "EmbeddingError",
    "InvalidMetadataError",
    "AccessDeniedError",
    "VersionConflictError",
    # Core Entities
    "Tenant",
    "KnowledgeBase",
    "Document",
    "DocumentVersion",
    "Chunk",
    # Access Control
    "AccessContext",
    # Search
    "SearchRequest",
    "SearchResult",
    # Legacy compatibility (deprecated)
    "ChunkMetadata",
    "SearchFilter",
    "SearchQuery",
]
