"""Inspect ChromaDB chunk data and metadata."""
import json
import os
import sqlite3
import sys

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "chroma", "chroma.sqlite3",
)


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Collections
    print("=" * 60)
    print("COLLECTIONS")
    print("=" * 60)
    c.execute("SELECT * FROM collections")
    cols = [d[0] for d in c.description]
    for row in c.fetchall():
        d = dict(zip(cols, row))
        print(f"  name={d.get('name')}  dimension={d.get('dimension')}")

    # 2. Segments
    print(f"\n{'=' * 60}")
    print("SEGMENTS")
    print("=" * 60)
    c.execute("SELECT * FROM segments")
    seg_cols = [d[0] for d in c.description]
    for row in c.fetchall():
        d = dict(zip(seg_cols, row))
        print(f"  id={d.get('id')}  scope={d.get('scope')}  type={d.get('type')}")

    # 3. Chunk content + metadata from embeddings_queue
    print(f"\n{'=' * 60}")
    print("CHUNKS (from embeddings_queue)")
    print("=" * 60)
    c.execute("SELECT id, metadata FROM embeddings_queue ORDER BY id")
    rows = c.fetchall()
    if not rows:
        print("  (empty)")
    for row in rows:
        chunk_id = row[0]
        meta_json = row[1]
        meta = json.loads(meta_json) if meta_json else {}
        # Document content is stored under 'chroma:document' key
        content = meta.pop("chroma:document", "")
        print(f"\n  --- chunk_id={chunk_id} ---")
        print(f"  Content ({len(content)} chars):")
        preview = content[:200].replace("\n", "\\n")
        print(f"    {preview}{'...' if len(content) > 200 else ''}")
        print(f"  Metadata:")
        for k, v in meta.items():
            print(f"    {k}: {v}")

    # 4. Structured metadata from embedding_metadata
    print(f"\n{'=' * 60}")
    print("STRUCTURED METADATA (from embedding_metadata)")
    print("=" * 60)
    try:
        c.execute("SELECT * FROM embedding_metadata ORDER BY id LIMIT 20")
        meta_cols = [d[0] for d in c.description]
        print(f"  Columns: {meta_cols}")
        for row in c.fetchall():
            d = dict(zip(meta_cols, row))
            print(f"  id={d.get('id')} key={d.get('key')} "
                  f"string={d.get('string_value')} int={d.get('int_value')} "
                  f"float={d.get('float_value')} bool={d.get('bool_value')}")
    except sqlite3.OperationalError as e:
        print(f"  Error: {e}")

    # 5. Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    c.execute("SELECT COUNT(*) FROM embeddings_queue")
    print(f"  Total chunks: {c.fetchone()[0]}")

    # Show unique metadata keys across all chunks
    c.execute("SELECT metadata FROM embeddings_queue")
    all_keys = set()
    for (meta_json,) in c.fetchall():
        if meta_json:
            meta = json.loads(meta_json)
            all_keys.update(k for k in meta.keys() if k != "chroma:document")
    print(f"  Metadata keys: {sorted(all_keys)}")

    conn.close()


if __name__ == "__main__":
    main()
