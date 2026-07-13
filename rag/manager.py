"""RAG Manager — unified entry point for RAG operations."""
from typing import Dict, List, Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from .documents import DocumentLoader, TextSplitter
from .embedding.local import create_embeddings
from .retriever import VectorRetriever


class RAGManager:
    """Unified entry point for RAG operations.

    Manages document loading, splitting, embedding, and retrieval
    with metadata filtering support.
    """

    def __init__(
        self,
        embedding: Optional[Embeddings] = None,
        collection_name: str = "default",
        persist_directory: str = "data/chroma",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        default_k: int = 4,
    ):
        self._embedding = embedding or create_embeddings()
        self._splitter = TextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        self._retriever = VectorRetriever(
            embedding=self._embedding,
            collection_name=collection_name,
            persist_directory=persist_directory,
            default_k=default_k,
        )

    def ingest_file(
        self,
        file_path: str,
        source_url: str = "",
        tags: str = "",
        category: str = "",
    ) -> int:
        """Load, split, and index a single file. Returns chunk count.

        Args:
            file_path: Path to the file to ingest.
            source_url: Original URL if document was fetched from web.
            tags: Comma-separated tags for categorization.
            category: Top-level category (e.g. "knowledge", "policy", "faq").
        """
        documents = DocumentLoader.load_file(
            file_path, source_url=source_url, tags=tags, category=category,
        )
        chunks = self._splitter.split(documents)
        if chunks:
            self._retriever.add_documents(chunks)
        return len(chunks)

    def search(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict] = None,
    ) -> List[Document]:
        """Search the knowledge base for relevant documents.

        Args:
            query: Search query text.
            k: Number of results to return.
            filter: ChromaDB where filter for metadata filtering, e.g.:
                - {"doc_type": "markdown"}
                - {"category": {"$in": ["knowledge", "faq"]}}
                - {"created_at": {"$gte": "2025-01-01"}}
                - {"$and": [{"doc_type": "markdown"}, {"tags": {"$in": ["agent"]}}]}
        """
        return self._retriever.retrieve(query, k=k, filter=filter)

    def delete_document(self, doc_id: str) -> None:
        """Delete all chunks belonging to a document."""
        self._retriever.delete_by_doc_id(doc_id)

    def delete_collection(self) -> None:
        """Delete the entire collection and all its data."""
        self._retriever.delete_collection()

    @property
    def document_count(self) -> int:
        """Return the number of indexed document chunks."""
        return self._retriever.document_count
