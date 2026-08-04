"""ChromaDB vector store with metadata filtering support."""
from typing import Dict, List, Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma


class ChromaVectorStore:
    """ChromaDB-based vector store for document storage and retrieval.

    Supports metadata filtering via ChromaDB's where clause syntax.
    """

    def __init__(
        self,
        embedding: Embeddings,
        collection_name: str = "default",
        persist_directory: str = "data/chroma",
    ):
        self._embedding = embedding
        self._collection_name = collection_name
        self._persist_directory = persist_directory
        self._store: Optional[Chroma] = None

    def _get_or_create_store(self) -> Chroma:
        """Get existing store or create a new one."""
        if self._store is None:
            self._store = Chroma(
                collection_name=self._collection_name,
                embedding_function=self._embedding,
                persist_directory=self._persist_directory,
            )
        return self._store

    def add_documents(self, documents: List[Document]) -> List[str]:
        """Add documents with metadata to the vector store."""
        store = self._get_or_create_store()
        # Use chunk_id as the document ID if available
        ids = [
            doc.metadata.get("chunk_id", None)
            for doc in documents
        ]
        # Filter out None ids and let ChromaDB auto-generate them
        ids = [i if i else None for i in ids]
        if all(ids):
            return store.add_documents(documents, ids=ids)
        return store.add_documents(documents)

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict] = None,
    ) -> List[Document]:
        """Search for similar documents, optionally filtered by metadata.

        Args:
            query: Search query text.
            k: Number of results to return.
            filter: ChromaDB where filter dict, e.g.
                {"doc_type": "markdown"}
                {"category": {"$in": ["knowledge", "faq"]}}
                {"created_at": {"$gte": "2025-01-01"}}
                {"$and": [{"doc_type": "markdown"}, {"tags": {"$in": ["agent"]}}]}
        """
        store = self._get_or_create_store()
        kwargs = {"k": k}
        if filter:
            kwargs["filter"] = filter
        return store.similarity_search(query, **kwargs)

    def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all chunks belonging to a document."""
        store = self._get_or_create_store()
        # ChromaDB supports where-based deletion
        store._collection.delete(where={"doc_id": doc_id})

    def delete_collection(self) -> None:
        """Delete the entire collection."""
        store = self._get_or_create_store()
        store.delete_collection()
        self._store = None

    @property
    def document_count(self) -> int:
        """Return the number of documents in the store."""
        store = self._get_or_create_store()
        return len(store.get()["ids"])
