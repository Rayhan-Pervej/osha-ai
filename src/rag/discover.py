import logging
import re

from src.config import settings
from src.exceptions.errors import OshaNoResultsError
from src.retrieval.bm25 import get_index, _tokenise
from src.utils.extract_relevant_texts import extract_relevant_window

logger = logging.getLogger(__name__)

REGULATORY_PARTS = {
    "1910": "29 CFR Part 1910 (General Industry Standards)",
    "1926": "29 CFR Part 1926 (Construction Standards)",
    "1904": "29 CFR Part 1904 (Recording and Reporting)",
    "1903": "29 CFR Part 1903 (Inspection Procedures)",
    "1902": "29 CFR Part 1902",
    "1900": "29 CFR Part 1900",
    "1911": "29 CFR Part 1911",
    "1915": "29 CFR Part 1915 (Shipyard Employment)",
    "1917": "29 CFR Part 1917 (Marine Terminals)",
    "1918": "29 CFR Part 1918 (Longshoring)",
    "1928": "29 CFR Part 1928 (Agriculture)",
    "FOM":  "OSHA Field Operations Manual",
    "OSH":  "Occupational Safety and Health Act",
}


def _detect_ambiguity(results: list) -> dict | None:
    """Check if top results span 2+ different CFR parts (e.g. 1910 vs 1926)."""
    if len(results) < 2:
        return None

    top_results = [r for r in results if r['score'] >= .60]
    cfr_parts = set()

    for r in top_results:
        part = _get_cfr_part(r["section_id"])
        if part:
            cfr_parts.add(part)

    if len(cfr_parts) < 2:
        return None

    labels = [REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in sorted(cfr_parts)]
    return {
        "parts": list(cfr_parts),
        "message": (
            f"Your query matches regulations in multiple regulatory parts: {' and '.join(labels)}. "
            f"Please clarify which applies to your situation before we proceed:\n"
            + "\n".join(f"  • {l}" for l in labels)
        ),
    }


def _get_cfr_part(section_id: str) -> str | None:
    """Extract CFR part prefix from a section_id (e.g. '1910.132' → '1910')."""
    for prefix in REGULATORY_PARTS:
        if section_id.startswith(prefix) and prefix not in ("FOM", "OSH"):
            return prefix
    return None


def _score_label(score: float) -> str:
    if score >= 0.90:
        return "High"
    if score >= 0.75:
        return "Medium"
    return "Low"


def discover(query: str, part_filter: str | None = None) -> dict:
    """Run a BM25 keyword search and return ranked results with optional part filtering."""
    _index, _docs = get_index()

    top_k     = settings.BEDROCK_RETRIEVAL_TOP_K
    min_score = settings.BEDROCK_RETRIEVAL_MIN_SCORE

    query_tokens = _tokenise(query, strip_stops=True)
    raw_scores   = _index.get_scores(query_tokens)

    max_score  = float(max(raw_scores)) if max(raw_scores) > 0 else 1.0
    normalised = [s / max_score for s in raw_scores]

    scored = [
        (normalised[i], _docs[i])
        for i in range(len(_docs))
        if normalised[i] >= min_score
        and (part_filter is None or _get_cfr_part(_docs[i]['section_id']) == part_filter)
    ]

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:top_k]

    if not scored:
        raise OshaNoResultsError(f"No results found for query: {query!r}")

    results = []
    for score, doc in scored:
        score = round(score, 4)
        results.append({
            "section_id": doc["section_id"],
            "source":     doc["source"],
            "title":      doc["title"],
            "path":       doc["path"],
            "local_path": doc["local_path"],
            # excerpt uses raw_content — clean text, no BM25 prefix noise
            "excerpt":    extract_relevant_window(doc["raw_content"], query, max_chars=500),
            "score":      score,
            "relevance":  _score_label(score),
        })

    if part_filter is None:
        ambiguity = _detect_ambiguity(results)
        if ambiguity:
            parts = ambiguity["parts"]
            return {
                "query":         query,
                "ambiguous":     True,
                "parts_found":   parts,
                "parts_labels":  {p: REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in parts},
                "clarification": ambiguity["message"],
                "results":       results,
            }

    return {
        "query":         query,
        "ambiguous":     False,
        "total_results": len(results),
        "results":       results,
        "next_step":     "Reply with the section_id(s) you want to lock for a detailed compliance answer.",
    }
