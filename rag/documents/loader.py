"""Document loading utilities."""
import hashlib
import os
from datetime import datetime
from typing import List, Optional

from langchain_core.documents import Document as LCDocument

from rag.domain import (
    Category,
    DocumentNotFoundError,
    DocumentType,
    UnsupportedDocumentTypeError,
)


class DocumentLoader:
    """Load documents from files (txt, md) and directories."""

    @staticmethod
    def _compute_doc_id(path: str) -> str:
        """Generate deterministic doc_id from file path."""
        return hashlib.md5(os.path.abspath(path).encode()).hexdigest()[:16]

    @staticmethod
    def load_file(
        file_path: str,
        source_url: Optional[str] = None,
        tags: Optional[list[str]] = None,
        category: Optional[Category] = None,
    ) -> List[LCDocument]:
        """Load a single file as a list of LangChain Document objects with rich metadata.

        Args:
            file_path: Path to the file to load.
            source_url: Optional URL where the document was fetched from.
            tags: Optional list of tags for categorization.
            category: Optional category enum value.

        Returns:
            List containing a single LangChain Document with the file content and metadata.

        Raises:
            DocumentNotFoundError: If file doesn't exist.
            UnsupportedDocumentTypeError: If file type is not supported.
        """
        path = os.path.abspath(file_path)
        if not os.path.exists(path):
            raise DocumentNotFoundError(f"File not found: {path}")

        ext = os.path.splitext(path)[1].lower()
        doc_type = DocumentType.from_extension(ext)

        # Check if supported
        if doc_type not in (DocumentType.TEXT, DocumentType.MARKDOWN):
            raise UnsupportedDocumentTypeError(
                f"Unsupported file type: {ext}. "
                f"Supported: .txt, .md"
            )

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        # Get file stats
        stat = os.stat(path)
        doc_id = DocumentLoader._compute_doc_id(path)

        # Create metadata dict for LangChain Document
        metadata_dict = {
            "doc_id": doc_id,
            "source": path,
            "doc_type": doc_type.value,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "source_url": source_url or "",
            "tags": ",".join(tags) if tags else "",
            "category": category.value if category else "",
        }

        return [LCDocument(page_content=text, metadata=metadata_dict)]
