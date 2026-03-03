import logging
from langchain_core.tools import tool

from src.config import settings
from src.retrieval.bm25 import get_index, _tokenise
from src.utils.extract_relevant_texts import extract_relevant_window
from src.agent.tools.registry import REGULATORY_PARTS, get_cfr_part
from src.exceptions.errors import OshaNoResultsError

logger = logging.getLogger(__name__)


def _score_label(score: float) -> str:
    """Human-readable relevance label."""
    if score >= 0.90:
        return "High"
    if score >= 0.75:
        return "Medium"
    return "Low"


def _detect_ambiguity(results: list[dict]) -> dict | None:
    """Check if top results span 2+ different CFR parts (e.g. 1910 vs 1926).

    When results come from multiple parts, the agent should ask the user
    which industry applies before proceeding.
    """
    if len(results) < 2:
        return None

    top_results = [r for r in results if r["score"] >= 0.60]
    cfr_parts = set()
    for r in top_results:
        part = get_cfr_part(r["section_id"])
        if part:
            cfr_parts.add(part)

    if len(cfr_parts) < 2:
        return None

    labels = [REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in sorted(cfr_parts)]
    return {
        "parts": sorted(cfr_parts),
        "parts_labels": {p: REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in sorted(cfr_parts)},
        "message": (
            f"Your query matches regulations in multiple regulatory parts: {' and '.join(labels)}. "
            f"Please clarify which applies to your situation before we proceed:\n"
            + "\n".join(f"  - {label}" for label in labels)
        ),
    }

def discover(query: str, part_filter: str | None = None) -> dict:
    """Run a BM25 keyword search and return ranked, structured results.

    Returns a dict with:
      - query: the search query
      - ambiguous: bool — whether results span multiple CFR parts
      - results: list of dicts with section_id, source, title, path, excerpt, score, relevance
      - clarification: (if ambiguous) message asking which part applies
      - total_results: count

    Raises OshaNoResultsError if nothing matches.
    """
    _index, _docs = get_index()

    top_k = settings.BEDROCK_RETRIEVAL_TOP_K
    min_score = settings.BEDROCK_RETRIEVAL_MIN_SCORE

    query_tokens = _tokenise(query, strip_stops=True)
    raw_scores = _index.get_scores(query_tokens)

    max_score = float(max(raw_scores)) if max(raw_scores) > 0 else 1.0
    normalised = [s / max_score for s in raw_scores]

    scored = [
        (normalised[i], _docs[i])
        for i in range(len(_docs))
        if normalised[i] >= min_score
        and (part_filter is None or get_cfr_part(_docs[i]["section_id"]) == part_filter)
    ]

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:top_k]

    # Deduplicate: keep best chunk per section_id
    seen = {}
    for score, doc in scored:
        sid = doc["section_id"]
        if sid not in seen or score > seen[sid][0]:
            seen[sid] = (score, doc)
    scored = list(seen.values())
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        raise OshaNoResultsError(f"No results found for query: {query!r}")

    # Pre-compute section sizes (total chars across all chunks per section)
    section_chars = {}
    section_chunk_count = {}
    for doc in _docs:
        sid = doc["section_id"]
        section_chars[sid] = section_chars.get(sid, 0) + len(doc["raw_content"])
        section_chunk_count[sid] = section_chunk_count.get(sid, 0) + 1

    results = []
    for score, doc in scored:
        score = round(float(score), 4)
        sid = doc["section_id"]
        results.append({
            "section_id":  sid,
            "source":      doc.get("source", ""),
            "title":       doc.get("title", ""),
            "path":        doc.get("path", ""),
            "local_path":  doc.get("local_path", ""),
            "excerpt":     extract_relevant_window(doc["raw_content"], query, max_chars=500),
            "score":       score,
            "relevance":   _score_label(score),
            "total_chars": section_chars.get(sid, 0),
            "chunk_count": section_chunk_count.get(sid, 0),
        })

    if part_filter is None:
        ambiguity = _detect_ambiguity(results)
        if ambiguity:
            return {
                "query":         query,
                "ambiguous":     True,
                "parts_found":   ambiguity["parts"],
                "parts_labels":  ambiguity["parts_labels"],
                "clarification": ambiguity["message"],
                "results":       results,
            }

    return {
        "query":         query,
        "ambiguous":     False,
        "total_results": len(results),
        "results":       results,
    }



@tool
def search_regulations(query: str, part_filter: str | None = None) -> str:
    """Search OSHA regulations by keyword to find relevant sections.

    Performs a BM25 keyword search across the full OSHA regulatory corpus.
    Returns matching sections ranked by relevance, with scores and contextual
    excerpts to help identify the right regulation.

    When results span multiple parts (e.g. 1910 General Industry AND 1926
    Construction), the output will flag this so you can ask the user which
    industry applies.

    You can call this tool multiple times with different queries to find
    more results or narrow down the search.

    Args:
        query: Search keywords describing the safety topic or hazard.
               Be specific for better results.
               Good: "scaffolding fall protection guardrail requirements"
               Okay: "fall protection"
               Too vague: "safety"
        part_filter: Optional OSHA part number to restrict search scope.
                     Examples: "1910" (General Industry), "1926" (Construction)
                     Omit to search across all parts.
    """
    try:
        result = discover(query, part_filter=part_filter)
    except OshaNoResultsError:
        filter_note = f" in Part {part_filter}" if part_filter else ""
        return (
            f"No results found for '{query}'{filter_note}.\n"
            "Suggestions:\n"
            "  - Try different keywords or synonyms\n"
            "  - Remove the part_filter to search all parts\n"
            "  - Search with broader or different keywords"
        )

    # Format output for the agent
    filter_note = f" (Part {part_filter})" if part_filter else ""
    lines = [f"Search results for '{query}'{filter_note}:\n"]

    # Flag cross-part ambiguity
    if result.get("ambiguous"):
        lines.append(f"NOTE: {result['clarification']}\n")

    for i, r in enumerate(result["results"], 1):
        part = get_cfr_part(r["section_id"]) or ""
        part_label = f" [{REGULATORY_PARTS.get(part, '')}]" if part else ""
        excerpt = r["excerpt"][:500]
        total_chars = r.get("total_chars", 0)
        size_note = " [LARGE SECTION — ask user to clarify sub-topic before calling generate_answer]" if total_chars > 40_000 else ""
        lines.append(
            f"{i}. Section {r['section_id']} — {r.get('title', 'Untitled')}{part_label}{size_note}\n"
            f"   Relevance: {r['relevance']} ({r['score']:.0%})\n"
            f"   Section size: {total_chars:,} chars ({r.get('chunk_count', '?')} chunks)\n"
            f"   Excerpt: {excerpt}\n"
        )

    return "\n".join(lines)
