"""Domain models for RAG system.

Enterprise-grade domain models for multi-tenant RAG system with
knowledge base management, document versioning, and access control.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .enums import DocumentType, Category


# ============================================================================
# Core Entities
# ============================================================================


@dataclass
class Tenant:
    """Multi-tenant isolation entity.

    Represents a tenant (organization/workspace) that owns knowledge bases.
    All data is isolated by tenant_id.
    """
    tenant_id: str
    name: str
    created_at: datetime
    settings: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str, tenant_id: Optional[str] = None) -> Tenant:
        """Create a new tenant."""
        return cls(
            tenant_id=tenant_id or f"tenant_{uuid.uuid4().hex[:12]}",
            name=name,
            created_at=datetime.now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "settings": self.settings,
            "metadata": self.metadata,
        }


@dataclass
class KnowledgeBase:
    """Knowledge base entity.

    A collection of documents within a tenant. Supports:
    - Tenant isolation
    - Access control
    - Embedding configuration
    - Metadata filtering
    """
    kb_id: str
    tenant_id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    embedding_model: str = "default"
    chunk_size: int = 500
    chunk_overlap: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        tenant_id: str,
        name: str,
        description: str = "",
        kb_id: Optional[str] = None,
        embedding_model: str = "default",
    ) -> KnowledgeBase:
        """Create a new knowledge base."""
        now = datetime.now()
        return cls(
            kb_id=kb_id or f"kb_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            embedding_model=embedding_model,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_id": self.kb_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "embedding_model": self.embedding_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "metadata": self.metadata,
        }


@dataclass
class Document:
    """Document entity.

    Represents a source document within a knowledge base.
    Supports versioning - see DocumentVersion for version history.
    """
    doc_id: str
    kb_id: str
    tenant_id: str
    title: str
    source: str
    doc_type: DocumentType
    created_at: datetime
    updated_at: datetime
    current_version: int = 1
    source_url: Optional[str] = None
    category: Optional[Category] = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        kb_id: str,
        tenant_id: str,
        title: str,
        source: str,
        doc_type: DocumentType,
        doc_id: Optional[str] = None,
        source_url: Optional[str] = None,
        category: Optional[Category] = None,
        tags: Optional[list[str]] = None,
    ) -> Document:
        """Create a new document."""
        now = datetime.now()
        return cls(
            doc_id=doc_id or f"doc_{uuid.uuid4().hex[:12]}",
            kb_id=kb_id,
            tenant_id=tenant_id,
            title=title,
            source=source,
            doc_type=doc_type,
            created_at=now,
            updated_at=now,
            source_url=source_url,
            category=category,
            tags=tags or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "kb_id": self.kb_id,
            "tenant_id": self.tenant_id,
            "title": self.title,
            "source": self.source,
            "doc_type": self.doc_type.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "current_version": self.current_version,
            "source_url": self.source_url or "",
            "category": self.category.value if self.category else "",
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class DocumentVersion:
    """Document version entity.

    Tracks version history of documents. Each update creates a new version.
    Enables rollback, version comparison, and audit trail.
    """
    version_id: str
    doc_id: str
    version_number: int
    content: str
    content_hash: str
    created_at: datetime
    created_by: Optional[str] = None
    change_summary: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        doc_id: str,
        version_number: int,
        content: str,
        content_hash: str,
        version_id: Optional[str] = None,
        created_by: Optional[str] = None,
        change_summary: Optional[str] = None,
    ) -> DocumentVersion:
        """Create a new document version."""
        return cls(
            version_id=version_id or f"ver_{uuid.uuid4().hex[:12]}",
            doc_id=doc_id,
            version_number=version_number,
            content=content,
            content_hash=content_hash,
            created_at=datetime.now(),
            created_by=created_by,
            change_summary=change_summary,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "doc_id": self.doc_id,
            "version_number": self.version_number,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by or "",
            "change_summary": self.change_summary or "",
            "metadata": self.metadata,
        }


@dataclass
class Chunk:
    """Document chunk entity.

    Represents a chunk of a document version, stored in the vector database.
    Links back to specific document version for traceability.
    """
    chunk_id: str
    doc_id: str
    version_id: str
    kb_id: str
    tenant_id: str
    chunk_index: int
    content: str
    embedding_vector: Optional[list[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        doc_id: str,
        version_id: str,
        kb_id: str,
        tenant_id: str,
        chunk_index: int,
        content: str,
        chunk_id: Optional[str] = None,
        embedding_vector: Optional[list[float]] = None,
    ) -> Chunk:
        """Create a new chunk."""
        return cls(
            chunk_id=chunk_id or f"chunk_{uuid.uuid4().hex[:16]}",
            doc_id=doc_id,
            version_id=version_id,
            kb_id=kb_id,
            tenant_id=tenant_id,
            chunk_index=chunk_index,
            content=content,
            embedding_vector=embedding_vector,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to flat dict for vector store metadata."""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "version_id": self.version_id,
            "kb_id": self.kb_id,
            "tenant_id": self.tenant_id,
            "chunk_index": self.chunk_index,
            "created_at": self.created_at.isoformat(),
            **self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], content: str = "") -> Chunk:
        """Reconstruct from vector store metadata."""
        return cls(
            chunk_id=data["chunk_id"],
            doc_id=data["doc_id"],
            version_id=data["version_id"],
            kb_id=data["kb_id"],
            tenant_id=data["tenant_id"],
            chunk_index=int(data["chunk_index"]),
            content=content,
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata={k: v for k, v in data.items()
                     if k not in {"chunk_id", "doc_id", "version_id", "kb_id",
                                 "tenant_id", "chunk_index", "created_at"}},
        )


# ============================================================================
# Access Control & Context
# ============================================================================


@dataclass
class AccessContext:
    """Access context for permission checking.

    Carries user identity and permissions for authorization.
    Used in search and document operations to enforce access control.
    """
    tenant_id: str
    user_id: Optional[str] = None
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    kb_access: dict[str, list[str]] = field(default_factory=dict)  # kb_id -> permissions
    metadata: dict[str, Any] = field(default_factory=dict)

    def can_access_kb(self, kb_id: str, permission: str = "read") -> bool:
        """Check if user can access a knowledge base."""
        if kb_id not in self.kb_access:
            return False
        return permission in self.kb_access[kb_id]

    def can_access_tenant(self, tenant_id: str) -> bool:
        """Check if user belongs to tenant."""
        return self.tenant_id == tenant_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id or "",
            "roles": self.roles,
            "permissions": self.permissions,
            "kb_access": self.kb_access,
            "metadata": self.metadata,
        }


# ============================================================================
# Search & Query
# ============================================================================


@dataclass
class SearchRequest:
    """Search request entity.

    Encapsulates all search parameters including tenant context,
    knowledge base scope, filters, and pagination.
    """
    query_text: str
    access_context: AccessContext
    kb_ids: list[str] = field(default_factory=list)  # Empty = search all accessible KBs
    top_k: int = 4
    min_score: Optional[float] = None
    doc_type_filter: Optional[DocumentType] = None
    category_filter: Optional[Category] = None
    tags_filter: Optional[list[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    metadata_filter: dict[str, Any] = field(default_factory=dict)

    def get_accessible_kb_ids(self) -> list[str]:
        """Get list of knowledge base IDs user can access."""
        if self.kb_ids:
            # Filter requested KBs by access permissions
            return [
                kb_id for kb_id in self.kb_ids
                if self.access_context.can_access_kb(kb_id)
            ]
        # Return all accessible KBs
        return list(self.access_context.kb_access.keys())

    def to_vector_filter(self) -> dict[str, Any]:
        """Convert to ChromaDB where filter format with tenant isolation."""
        conditions = []

        # CRITICAL: Always filter by tenant_id for isolation
        conditions.append({"tenant_id": self.access_context.tenant_id})

        # Filter by accessible knowledge bases
        accessible_kb_ids = self.get_accessible_kb_ids()
        if accessible_kb_ids:
            if len(accessible_kb_ids) == 1:
                conditions.append({"kb_id": accessible_kb_ids[0]})
            else:
                conditions.append({"kb_id": {"$in": accessible_kb_ids}})

        # Document type filter
        if self.doc_type_filter:
            conditions.append({"doc_type": self.doc_type_filter.value})

        # Category filter
        if self.category_filter:
            conditions.append({"category": self.category_filter.value})

        # Tags filter (any tag match)
        if self.tags_filter:
            conditions.append({"tags": {"$in": self.tags_filter}})

        # Date range filters
        if self.date_from:
            conditions.append({"created_at": {"$gte": self.date_from.isoformat()}})
        if self.date_to:
            conditions.append({"created_at": {"$lte": self.date_to.isoformat()}})

        # Custom metadata filters
        for key, value in self.metadata_filter.items():
            conditions.append({key: value})

        # Combine all conditions with $and
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_text": self.query_text,
            "kb_ids": self.kb_ids,
            "top_k": self.top_k,
            "min_score": self.min_score,
            "doc_type_filter": self.doc_type_filter.value if self.doc_type_filter else None,
            "category_filter": self.category_filter.value if self.category_filter else None,
            "tags_filter": self.tags_filter,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
        }


@dataclass
class SearchResult:
    """Search result entity.

    Represents a single search result with chunk content, metadata,
    and relevance score. Links back to source document and version.
    """
    chunk: Chunk
    score: float
    document: Optional[Document] = None  # Enriched with document info
    highlights: list[str] = field(default_factory=list)

    @property
    def content(self) -> str:
        """Get chunk content."""
        return self.chunk.content

    @property
    def doc_id(self) -> str:
        """Get document ID."""
        return self.chunk.doc_id

    @property
    def kb_id(self) -> str:
        """Get knowledge base ID."""
        return self.chunk.kb_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API response."""
        result = {
            "content": self.chunk.content,
            "score": self.score,
            "chunk_id": self.chunk.chunk_id,
            "chunk_index": self.chunk.chunk_index,
            "doc_id": self.chunk.doc_id,
            "version_id": self.chunk.version_id,
            "kb_id": self.chunk.kb_id,
            "highlights": self.highlights,
        }

        # Include document info if available
        if self.document:
            result["document"] = {
                "title": self.document.title,
                "source": self.document.source,
                "doc_type": self.document.doc_type.value,
                "category": self.document.category.value if self.document.category else None,
                "tags": self.document.tags,
            }

        return result

    @classmethod
    def from_chunk_and_score(
        cls,
        chunk: Chunk,
        score: float,
        document: Optional[Document] = None,
    ) -> SearchResult:
        """Create search result from chunk and score."""
        return cls(
            chunk=chunk,
            score=score,
            document=document,
        )

    @classmethod
    def from_document(cls, doc: Any, score: Optional[float] = None) -> SearchResult:
        """Create from LangChain Document object (compatibility method).

        This is a temporary compatibility layer for the current RAG implementation
        that still uses LangChain Documents. Eventually should be replaced with
        proper Chunk entities.
        """
        from ..schema import ChunkMetadata

        # Extract metadata
        metadata = ChunkMetadata.from_dict(doc.metadata)

        # Create a minimal Chunk from LangChain Document
        # Note: This doesn't have full enterprise fields (tenant_id, kb_id, version_id)
        chunk = Chunk(
            chunk_id=metadata.chunk_id,
            doc_id=metadata.doc_id,
            version_id="",  # Not available in legacy data
            kb_id="",  # Not available in legacy data
            tenant_id="",  # Not available in legacy data
            chunk_index=metadata.chunk_index,
            content=doc.page_content,
            embedding_vector=None,
            created_at=datetime.fromisoformat(metadata.created_at) if metadata.created_at else datetime.now(),
        )

        return cls(
            chunk=chunk,
            score=score or 0.0,
            document=None,
            highlights=[],
        )


# ============================================================================
# Legacy/Compatibility Models (DEPRECATED)
# ============================================================================
# These models exist only for backward compatibility with existing code.
# New code should use the enterprise models above.
# Will be removed in future versions.


@dataclass
class SearchFilter:
    """Legacy search filter model.

    DEPRECATED: Use SearchRequest instead.
    """
    doc_type: Optional[DocumentType] = None
    category: Optional[Category] = None
    tags: Optional[list[str]] = None
    doc_id: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    custom: dict[str, Any] = field(default_factory=dict)

    def to_chroma_filter(self) -> dict[str, Any]:
        """Convert to ChromaDB where filter format."""
        conditions = []

        if self.doc_type:
            conditions.append({"doc_type": self.doc_type.value})

        if self.category:
            conditions.append({"category": self.category.value})

        if self.tags:
            conditions.append({"tags": {"$in": self.tags}})

        if self.doc_id:
            conditions.append({"doc_id": self.doc_id})

        if self.created_after:
            conditions.append({"created_at": {"$gte": self.created_after.isoformat()}})

        if self.created_before:
            conditions.append({"created_at": {"$lte": self.created_before.isoformat()}})

        for key, value in self.custom.items():
            conditions.append({key: value})

        if len(conditions) == 0:
            return {}
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}


@dataclass
class SearchQuery:
    """Legacy search query model.

    DEPRECATED: Use SearchRequest instead.
    """
    text: str
    k: int = 4
    filter: Optional[SearchFilter] = None

    def to_retrieval_params(self) -> dict[str, Any]:
        """Convert to params dict for retriever."""
        params = {
            "query": self.text,
            "k": self.k,
        }
        if self.filter:
            chroma_filter = self.filter.to_chroma_filter()
            if chroma_filter:
                params["filter"] = chroma_filter
        return params




