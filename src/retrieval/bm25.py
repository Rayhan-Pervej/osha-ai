import json
import logging
import os
import re

from rank_bm25 import BM25Okapi

from src.config import settings
from src.exceptions.errors import OshaIndexError, OshaDocumentNotFoundError
from src.utils.text import _STOP_WORDS, _stem

logger = logging.getLogger(__name__)

_index: BM25Okapi | None = None
_docs: list[dict] | None = None


def _tokenise(text: str, strip_stops: bool = False) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", text.lower())
    if strip_stops:
        tokens = [t for t in tokens if t not in _STOP_WORDS]
    return [_stem(t) for t in tokens]


def _load_index() -> tuple[BM25Okapi, list[dict]]:
    chunks_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "processed", "chunks.json"
    )

    if not os.path.exists(chunks_file):
        raise OshaIndexError(
            f"Chunks file not found: {chunks_file}. Run: python scripts/build_chunks.py"
        )

    with open(chunks_file, encoding="utf-8") as f:
        docs = json.load(f)

    logger.info(f"BM25: loading {len(docs)} chunks from {chunks_file}")

    tokenised = []
    for doc in docs:
        tokenised.append(_tokenise(
            f"{doc['section_id']} {doc['title']} {doc['raw_content']}"
        ))

    index = BM25Okapi(tokenised)
    logger.info(f"BM25: index ready — {len(docs)} chunks")
    return index, docs


def ensure_index():
    global _index, _docs
    if _index is None:
        _index, _docs = _load_index()


def get_index() -> tuple[BM25Okapi, list[dict]]:
    ensure_index()
    return _index, _docs


def get_raw_content(section_id: str) -> str:
    ensure_index()
    chunks = sorted(
        [doc for doc in _docs if doc["section_id"] == section_id],
        key=lambda d: d.get("chunk_index", 0)
    )
    if not chunks:
        raise OshaDocumentNotFoundError(f"Section not found in index: {section_id!r}")
    return "\n\n".join(c["raw_content"] for c in chunks)


def get_section_metadata(section_id: str) -> dict:
    ensure_index()
    for doc in _docs:
        if doc["section_id"] == section_id:
            return {
                "section_id": doc["section_id"],
                "source":     doc.get("source", ""),
                "title":      doc.get("title", ""),
                "path":       doc.get("path", ""),
                "local_path": doc.get("local_path", ""),
            }
    raise OshaDocumentNotFoundError(f"Section not found in index: {section_id!r}")


def get_top_chunks(section_id: str, query: str, max_chars: int) -> tuple[str, float]:
    """Return the most query-relevant chunks for a section, up to max_chars.

    Scores each chunk with a local BM25 index, greedily selects chunks in
    score order until the character budget is exhausted, then returns them
    joined in reading order (ascending chunk_index).

    Returns:
        (context_text, context_relevance) where context_relevance is the
        mean normalised BM25 score of selected chunks (0.0–1.0). This is
        the confidence signal: how relevant is the retrieved context to the query?
    """
    ensure_index()

    section_chunks = [doc for doc in _docs if doc["section_id"] == section_id]
    if not section_chunks:
        raise OshaDocumentNotFoundError(f"Section not found in index: {section_id!r}")

    # Short-circuit: single chunk — no BM25 ranking needed
    if len(section_chunks) == 1:
        raw = section_chunks[0]["raw_content"]
        if len(raw) > max_chars:
            raw = raw[:max_chars] + "\n[...truncated...]"
        return raw, 1.0

    # If entire section fits within budget — all chunks selected, use mean score
    total_chars = sum(len(doc["raw_content"]) for doc in section_chunks)
    if total_chars <= max_chars:
        logger.debug("[BM25] Section %s fits entirely (%d chars) — sending all %d chunks", section_id, total_chars, len(section_chunks))
        selected = sorted(section_chunks, key=lambda d: d.get("chunk_index", 0))
        # Compute mean BM25 score across all chunks for relevance signal
        query_tokens = _tokenise(query, strip_stops=True)
        local_corpus = [_tokenise(f"{doc['section_id']} {doc['title']} {doc['raw_content']}") for doc in section_chunks]
        local_index = BM25Okapi(local_corpus)
        raw_scores = local_index.get_scores(query_tokens)
        max_score = float(max(raw_scores)) if max(raw_scores) > 0 else 1.0
        normalised = [s / max_score for s in raw_scores]
        relevance = sum(normalised) / len(normalised)
        return "\n\n".join(c["raw_content"] for c in selected), relevance

    # Section exceeds budget — rank and select top chunks
    logger.debug("[BM25] Section %s exceeds budget (%d chars > %d) — ranking %d chunks", section_id, total_chars, max_chars, len(section_chunks))
    query_tokens = _tokenise(query, strip_stops=True)
    local_corpus = [
        _tokenise(f"{doc['section_id']} {doc['title']} {doc['raw_content']}")
        for doc in section_chunks
    ]
    local_index = BM25Okapi(local_corpus)
    raw_scores = local_index.get_scores(query_tokens)

    max_score = float(max(raw_scores)) if max(raw_scores) > 0 else 1.0
    normalised = [s / max_score for s in raw_scores]

    # only chunks scoring ≥ 30% of top chunk
    scored = sorted(
        [(normalised[i], section_chunks[i]) for i in range(len(section_chunks)) if normalised[i] >= 0.3],
        key=lambda x: x[0],
        reverse=True,
    )

    # Fall back
    if not scored:
        scored = sorted(zip(normalised, section_chunks), key=lambda x: x[0], reverse=True)

    # Greedy fill
    selected = []
    selected_scores = []
    chars_used = 0
    for score, doc in scored:
        content = doc["raw_content"]
        if chars_used + len(content) <= max_chars:
            selected.append(doc)
            selected_scores.append(score)
            chars_used += len(content)

    relevance = sum(selected_scores) / len(selected_scores) if selected_scores else 0.0

    # Restore reading order
    selected.sort(key=lambda d: d.get("chunk_index", 0))
    return "\n\n".join(c["raw_content"] for c in selected), relevance
