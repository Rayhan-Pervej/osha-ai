import chromadb
from chromadb.config import Settings
from pathlib import Path


DB_PATH     = Path("data/vector_store")
COLLECTION  = "osha_chunks"

_client     = None
_collection = None


def _get_collection():
    """Lazy-init ChromaDB client and collection."""
    global _client, _collection
    if _collection is None:
        DB_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(DB_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"}, 
        )
    return _collection


def add(chunk_id: str, embedding: list[float], text: str, metadata: dict):
    """
    Store one child chunk with its embedding.
    metadata should include: parent_id, source, title, section, path, source_file
    """
    col = _get_collection()
    col.add(
        ids=[chunk_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata],
    )


def add_batch(
    chunk_ids: list[str],
    embeddings: list[list[float]],
    texts: list[str],
    metadatas: list[dict],
):
    """Store multiple child chunks at once — faster than one by one."""
    col = _get_collection()
    col.add(
        ids=chunk_ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )


def search(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """
    Find top-K most similar child chunks to the query vector.

    Returns list of dicts:
    {
        "chunk_id":  str,
        "text":      str,
        "score":     float,   # cosine distance (0=identical, 2=opposite)
        "metadata":  dict,    # parent_id, source, title, section, path
    }
    """
    col = _get_collection()
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "distances", "metadatas"],
    )

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "chunk_id": results["ids"][0][i],
            "text":     results["documents"][0][i],
            "score":    round(1 - results["distances"][0][i], 4), 
            "metadata": results["metadatas"][0][i],
        })

    return hits


def count() -> int:
    """Return total number of chunks stored."""
    return _get_collection().count()