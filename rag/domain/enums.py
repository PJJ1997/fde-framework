"""Enums for RAG domain."""
from enum import Enum


class DocumentType(str, Enum):
    """Document type enumeration."""
    MARKDOWN = "markdown"
    TEXT = "text"
    PDF = "pdf"
    HTML = "html"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_extension(cls, ext: str) -> "DocumentType":
        """Infer document type from file extension."""
        ext_lower = ext.lower().lstrip(".")
        mapping = {
            "md": cls.MARKDOWN,
            "markdown": cls.MARKDOWN,
            "txt": cls.TEXT,
            "text": cls.TEXT,
            "pdf": cls.PDF,
            "html": cls.HTML,
            "htm": cls.HTML,
        }
        return mapping.get(ext_lower, cls.UNKNOWN)


class Category(str, Enum):
    """Document category enumeration."""
    KNOWLEDGE = "knowledge"
    POLICY = "policy"
    FAQ = "faq"
    TUTORIAL = "tutorial"
    API_DOC = "api_doc"
    RELEASE_NOTE = "release_note"
    TROUBLESHOOTING = "troubleshooting"
    OTHER = "other"


class KnowledgeBaseStatus(str, Enum):
    """Knowledge base status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    DELETED = "deleted"
