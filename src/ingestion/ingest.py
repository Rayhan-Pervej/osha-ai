import json
import time
from pathlib import Path

from src.retrieval import embedder, vector_store, bm25_index

CHUNKS_PATH  = Path("data/processed/chunks.json")
BATCH_SIZE   = 50   # embed + store 50 chunks at a time
SLEEP_BETWEEN_BATCHES = 0.5  # seconds — avoids Bedrock throttling


def run(chunks_path: Path = CHUNKS_PATH):
    print("Loading chunks...")
    with open(chunks_path, encoding="utf-8") as f:
        all_chunks = json.load(f)

    children = [c for c in all_chunks if c["chunk_type"] == "child"]
    print(f"  {len(children)} child chunks to embed")

    existing = vector_store.count()
    if existing > 0:
        print(f"  ChromaDB already has {existing} vectors — skipping embedding step")
    else:
        print("Embedding and storing in ChromaDB...")
        total = len(children)

        for i in range(0, total, BATCH_SIZE):
            batch = children[i : i + BATCH_SIZE]

            chunk_ids  = [c["chunk_id"] for c in batch]
            texts      = [c["text"] for c in batch]
            metadatas  = [
                {
                    "parent_id": c["parent_id"],
                    "source":    c["source"],
                    "title":     c["title"],
                    "section":   c["section"],
                    "path":      c["path"],
                }
                for c in batch
            ]

            embeddings = [embedder.embed(t) for t in texts]

            vector_store.add_batch(chunk_ids, embeddings, texts, metadatas)

            done = min(i + BATCH_SIZE, total)
            print(f"  [{done}/{total}] stored")

            time.sleep(SLEEP_BETWEEN_BATCHES)

        print(f"  ChromaDB done: {vector_store.count()} vectors")

    bm25_path = bm25_index.INDEX_DIR / "metadata.json"
    if bm25_path.exists():
        print("BM25 index already exists — skipping")
    else:
        print("Building BM25 index...")
        bm25_index.build(chunks_path)

    print("\nIngestion complete.")


if __name__ == "__main__":
    run()
