"""Text splitting utilities."""
import uuid
from typing import List, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextSplitter:
    """Split documents into chunks for embedding.

    Each chunk inherits parent document metadata and gets a unique chunk_id
    and chunk_index.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None,
    ):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
            length_function=len,
        )

    def split(self, documents: List[Document]) -> List[Document]:
        """Split a list of documents into chunks with enriched metadata."""
        chunks = []
        for doc in documents:
            doc_id = doc.metadata.get("doc_id", uuid.uuid4().hex[:16])
            splits = self._splitter.split_documents([doc])
            for idx, split in enumerate(splits):
                # Inherit all parent metadata
                meta = dict(split.metadata)
                # Add / override chunk-level fields
                meta["chunk_id"] = f"{doc_id}_{idx:04d}"
                meta["chunk_index"] = idx
                # Ensure doc_id is present
                if "doc_id" not in meta:
                    meta["doc_id"] = doc_id
                chunks.append(Document(page_content=split.page_content, metadata=meta))
        return chunks
