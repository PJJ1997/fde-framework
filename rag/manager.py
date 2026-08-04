"""RAG Manager — unified entry point for RAG operations."""
from typing import List, Optional

from langchain_core.embeddings import Embeddings

from .documents import DocumentLoader, TextSplitter
from .domain import Category, SearchFilter, SearchQuery, SearchResult
from .embedding import create_embeddings
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
        source_url: Optional[str] = None,
        tags: Optional[list[str]] = None,
        category: Optional[Category] = None,
    ) -> int:
        """Load, split, and index a single file. Returns chunk count.

        Args:
            file_path: Path to the file to ingest.
            source_url: Optional URL if document was fetched from web.
            tags: Optional list of tags for categorization.
            category: Optional category enum value.

        Returns:
            Number of chunks created and indexed.
        """
        documents = DocumentLoader.load_file(
            file_path=file_path,
            source_url=source_url,
            tags=tags,
            category=category,
        )
        chunks = self._splitter.split(documents)
        if chunks:
            self._retriever.add_documents(chunks)
        return len(chunks)

    def search(
        self,
        query: str,
        k: int = 4,
        filter: Optional[SearchFilter] = None,
    ) -> List[SearchResult]:
        """Search the knowledge base for relevant documents.

        Args:
            query: Search query text.
            k: Number of results to return.
            filter: Optional SearchFilter for metadata-based filtering.

        Returns:
            List of SearchResult objects with content and metadata.

        Example:
            >>> from rag.domain import SearchFilter, Category, DocumentType
            >>>
            >>> # Simple search
            >>> results = manager.search("What is RAG?")
            >>>
            >>> # Filter by document type
            >>> filter = SearchFilter(doc_type=DocumentType.MARKDOWN)
            >>> results = manager.search("What is RAG?", filter=filter)
            >>>
            >>> # Filter by category and tags
            >>> filter = SearchFilter(
            ...     category=Category.KNOWLEDGE,
            ...     tags=["agent", "rag"]
            ... )
            >>> results = manager.search("What is RAG?", filter=filter)
        """
        search_query = SearchQuery(text=query, k=k, filter=filter)
        documents = self._retriever.retrieve(search_query)

        # Convert LangChain Documents to SearchResult domain objects
        return [SearchResult.from_document(doc) for doc in documents]

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
