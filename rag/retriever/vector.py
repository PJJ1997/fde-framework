"""Vector-based retriever with metadata filtering."""
from typing import List

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from rag.domain import SearchQuery
from rag.vectorstore import ChromaVectorStore


class VectorRetriever:
    """Retriever that uses vector similarity search with metadata filtering."""

    def __init__(
        self,
        embedding: Embeddings,
        collection_name: str = "default",
        persist_directory: str = "data/chroma",
        default_k: int = 4,
    ):
        self._store = ChromaVectorStore(
            embedding=embedding,
            collection_name=collection_name,
            persist_directory=persist_directory,
        )
        self._default_k = default_k

    def retrieve(self, search_query: SearchQuery) -> List[Document]:
        """Retrieve documents based on search query.

        Args:
            search_query: SearchQuery domain object with text, k, and filter.

        Returns:
            List of LangChain Document objects.
        """
        params = search_query.to_retrieval_params()
        return self._store.similarity_search(**params)

    def add_documents(self, documents) -> List[str]:
        """Add documents to the underlying vector store."""
        return self._store.add_documents(documents)

    def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all chunks belonging to a document."""
        self._store.delete_by_doc_id(doc_id)

    def delete_collection(self) -> None:
        """Delete the entire collection and all its data."""
        self._store.delete_collection()

    @property
    def document_count(self) -> int:
        return self._store.document_count
