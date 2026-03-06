from src.retrieval import vector_store, bm25_index

RRF_K = 60  # standard 


def search(query: str, query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """
    Hybrid search: vector (semantic) + BM25 (lexical) merged with RRF.

    Args:
        query:           raw query string (for BM25)
        query_embedding: embedded query vector (for ChromaDB)
        top_k:           number of final results to return

    Returns:
        list of dicts: chunk_id, parent_id, text, score, metadata
    """
    fetch_k = top_k * 4  # fetch more from each side before merging

    vec_hits = vector_store.search(query_embedding, top_k=fetch_k)
    bm25_hits = bm25_index.search(query, top_k=fetch_k)

    # --- RRF merge ---
    rrf_scores = {}   # chunk_id -> accumulated RRF score
    chunk_data  = {}  # chunk_id -> hit dict (to reconstruct final list)

    for rank, hit in enumerate(vec_hits):
        cid = hit["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        chunk_data[cid] = hit

    for rank, hit in enumerate(bm25_hits):
        cid = hit["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        if cid not in chunk_data:
            chunk_data[cid] = hit

    # sort by RRF score descending
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for cid, score in ranked[:top_k]:
        hit = chunk_data[cid].copy()
        hit["score"] = round(score, 6)
        results.append(hit)

    return results
