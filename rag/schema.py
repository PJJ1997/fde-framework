"""RAG schema — metadata model for document chunks."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class ChunkMetadata:
    """Metadata attached to every chunk stored in the vector store.

    Fields are designed to support both semantic search and metadata filtering.
    """

    # --- identity ---
    doc_id: str  # unique document identifier (same for all chunks of one document)
    chunk_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    chunk_index: int = 0  # 0-based index within the document

    # --- source ---
    source: str = ""  # original file path
    source_url: str = ""  # web URL if the document was fetched from the internet
    doc_type: str = ""  # e.g. "markdown", "text", "pdf", "html"

    # --- temporal ---
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )

    # --- categorization ---
    tags: str = ""  # comma-separated tags, e.g. "agent,rag,tool"
    category: str = ""  # top-level category, e.g. "knowledge", "policy", "faq"

    # --- extensible ---
    extra: str = ""  # JSON-serialized dict for any additional metadata

    def to_dict(self) -> Dict[str, str]:
        """Convert to a flat dict suitable for ChromaDB metadata (values must be str/int/float/bool)."""
        d = {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "source": self.source,
            "source_url": self.source_url,
            "doc_type": self.doc_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "category": self.category,
            "extra": self.extra,
        }
        return {k: v for k, v in d.items() if v != "" and v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> ChunkMetadata:
        """Reconstruct from a flat metadata dict."""
        return cls(
            doc_id=data.get("doc_id", ""),
            chunk_id=data.get("chunk_id", uuid.uuid4().hex[:16]),
            chunk_index=int(data.get("chunk_index", 0)),
            source=data.get("source", ""),
            source_url=data.get("source_url", ""),
            doc_type=data.get("doc_type", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=data.get("tags", ""),
            category=data.get("category", ""),
            extra=data.get("extra", ""),
        )
