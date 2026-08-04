"""Exceptions for RAG domain."""


class RAGError(Exception):
    """Base exception for RAG errors."""
    pass


class DocumentNotFoundError(RAGError):
    """Raised when a document is not found."""
    pass


class UnsupportedDocumentTypeError(RAGError):
    """Raised when document type is not supported."""
    pass


class VectorStoreError(RAGError):
    """Raised when vector store operation fails."""
    pass


class EmbeddingError(RAGError):
    """Raised when embedding generation fails."""
    pass


class InvalidMetadataError(RAGError):
    """Raised when metadata is invalid."""
    pass


class AccessDeniedError(RAGError):
    """Raised when user doesn't have permission to access a resource."""
    pass


class VersionConflictError(RAGError):
    """Raised when there's a document version conflict."""
    pass
