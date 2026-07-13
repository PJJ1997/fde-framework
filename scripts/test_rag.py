"""RAG verification script.

Ingests the LLM Agent knowledge base into ChromaDB and runs
sample searches to verify the RAG pipeline works end-to-end,
including metadata filtering.

Usage:
    python scripts/test_rag.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rag import RAGManager

KNOWLEDGE_FILE = os.path.join(os.path.dirname(__file__), "llm_agent_knowledge.md")


def ingest_documents():
    """Load knowledge file into vector store with metadata."""
    print(f"Loading: {KNOWLEDGE_FILE}")
    manager = RAGManager()
    # Clear existing data before ingest
    if manager.document_count > 0:
        print(f"  Clearing {manager.document_count} existing documents...")
        manager.delete_collection()
        # Recreate manager to reinitialize store
        manager = RAGManager()
    count = manager.ingest_file(
        KNOWLEDGE_FILE,
        tags="agent,llm,knowledge",
        category="knowledge",
    )
    print(f"  Ingested {count} chunks into vector store")
    print(f"  Total document count: {manager.document_count}")
    return manager


def search_tests(manager: RAGManager):
    """Run sample searches to verify retrieval quality and metadata filtering."""
    queries = [
        "Agent的ReAct架构是什么",
    ]

    print("\n--- Basic Search ---")
    for query in queries:
        print(f"\nQuery: {query}")
        results = manager.search(query, k=2)
        if not results:
            print("  (无结果)")
            continue
        for i, doc in enumerate(results, 1):
            doc_id = doc.metadata.get("doc_id", "")
            chunk_id = doc.metadata.get("chunk_id", "")
            category = doc.metadata.get("category", "")
            tags = doc.metadata.get("tags", "")
            content = doc.page_content[:120].replace("\n", " ")
            print(f"  [{i}] doc_id={doc_id} chunk_id={chunk_id}")
            print(f"      category={category} tags={tags}")
            print(f"      {content}...")

    # Metadata filtering test
    print("\n--- Filtered Search (category=knowledge) ---")
    results = manager.search("Agent", k=2, filter={"category": "knowledge"})
    for i, doc in enumerate(results, 1):
        chunk_id = doc.metadata.get("chunk_id", "")
        category = doc.metadata.get("category", "")
        print(f"  [{i}] chunk_id={chunk_id} category={category}")

    print("\n--- Filtered Search (doc_type=markdown) ---")
    results = manager.search("LLM", k=2, filter={"doc_type": "markdown"})
    for i, doc in enumerate(results, 1):
        chunk_id = doc.metadata.get("chunk_id", "")
        doc_type = doc.metadata.get("doc_type", "")
        print(f"  [{i}] chunk_id={chunk_id} doc_type={doc_type}")

    print()


if __name__ == "__main__":
    print("=== RAG Verification Script ===\n")

    print("Step 1: Ingest knowledge file into vector store")
    manager = ingest_documents()

    print("\nStep 2: Run search tests")
    search_tests(manager)

    print("=== Verification Complete ===")
