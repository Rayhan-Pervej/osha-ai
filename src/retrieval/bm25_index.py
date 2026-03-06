import json
import bm25s
from pathlib import Path

CHUNKS_PATH = Path("data/processed/chunks.json")
INDEX_DIR   = Path("data/bm25_index")

_retriever = None
_metadata  = None


def build(chunks_path: Path = CHUNKS_PATH, index_dir: Path = INDEX_DIR):
    """
    Reads chunks.json, builds a BM25s index over child chunk texts,
    saves index + metadata to disk.
    """
    with open(chunks_path, encoding="utf-8") as f:
        all_chunks = json.load(f)

    children = [c for c in all_chunks if c["chunk_type"] == "child"]

    if not children:
        raise ValueError("No child chunks found in chunks.json")

    texts = [c["text"] for c in children]

    # tokenize
    corpus_tokens = bm25s.tokenize(texts, stopwords="en")

    # build index
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)

    # save index to disk
    index_dir.mkdir(parents=True, exist_ok=True)
    retriever.save(str(index_dir))

    # save metadata separately (chunk_id, text, source_file, parent_id, etc.)
    meta = [
        {
            "chunk_id":   c["chunk_id"],
            "parent_id":  c["parent_id"],
            "text":       c["text"],
            "source":     c["source"],
            "title":      c["title"],
            "section":    c["section"],
            "path":       c["path"],
        }
        for c in children
    ]
    with open(index_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f)

    print(f"BM25 index built: {len(children)} child chunks -> {index_dir}")


def _load(index_dir: Path = INDEX_DIR):
    global _retriever, _metadata
    if _retriever is None:
        _retriever = bm25s.BM25.load(str(index_dir), load_corpus=False)
        with open(index_dir / "metadata.json", encoding="utf-8") as f:
            _metadata = json.load(f)




def search(query: str, top_k: int = 5) -> list[dict]:
    """
    Search the BM25 index.
    Returns list of dicts: chunk_id, text, score, metadata.
    """
    _load()

    query_tokens = bm25s.tokenize([query], stopwords="en")
    results, scores = _retriever.retrieve(query_tokens, k=top_k)

    # results shape: (n_queries, top_k)  — we have 1 query
    hits = []
    for idx, score in zip(results[0], scores[0]):
        meta = _metadata[idx]
        hits.append({
            "chunk_id": meta["chunk_id"],
            "parent_id": meta["parent_id"],
            "text":     meta["text"],
            "score":    float(score),
            "metadata": {
                "source":  meta["source"],
                "title":   meta["title"],
                "section": meta["section"],
                "path":    meta["path"],
            },
        })

    return hits