"""Document loading utilities."""
import hashlib
import os
from datetime import datetime
from typing import List
from langchain_core.documents import Document


class DocumentLoader:
    """Load documents from files (txt, md) and directories."""

    @staticmethod
    def _compute_doc_id(path: str) -> str:
        """Generate deterministic doc_id from file path."""
        return hashlib.md5(os.path.abspath(path).encode()).hexdigest()[:16]

    @staticmethod
    def load_file(
        file_path: str,
        source_url: str = "",
        tags: str = "",
        category: str = "",
    ) -> List[Document]:
        """Load a single file as a list of Document objects with rich metadata."""
        path = os.path.abspath(file_path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        ext = os.path.splitext(path)[1].lower()
        if ext not in (".txt", ".md"):
            raise ValueError(f"Unsupported file type: {ext}")

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        stat = os.stat(path)
        doc_id = DocumentLoader._compute_doc_id(path)
        doc_type = "markdown" if ext == ".md" else "text"

        metadata = {
            "doc_id": doc_id,
            "source": path,
            "source_url": source_url,
            "doc_type": doc_type,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "tags": tags,
            "category": category,
        }
        # Remove empty values to keep metadata clean
        metadata = {k: v for k, v in metadata.items() if v}

        return [Document(page_content=text, metadata=metadata)]
