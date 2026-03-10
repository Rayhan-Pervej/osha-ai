import json
import logging
from langchain_core.tools import tool

from src.config import settings
from src.retrieval import bedrock_kb
from src.agent.tools.registry import REGULATORY_PARTS, get_cfr_part
from src.exceptions.errors import OshaNoResultsError
from src.agent.tools.generate_answer import _build_osha_url

logger = logging.getLogger(__name__)


def _detect_ambiguity(results: list[dict]) -> dict | None:
    """
    Deterministic check: if top results span 2+ different CFR parts
    (e.g. 1910 vs 1926), flag as ambiguous so agent asks which industry.
    """
    if len(results) < 2:
        return None

    cfr_parts = set()
    for r in results:
        part = get_cfr_part(r.get("section", ""))
        if part:
            cfr_parts.add(part)

    if len(cfr_parts) < 2:
        return None

    labels = [REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in sorted(cfr_parts)]
    return {
        "parts":       sorted(cfr_parts),
        "parts_labels": {p: REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in sorted(cfr_parts)},
        "message": (
            f"Your query matches regulations in multiple regulatory parts: {' and '.join(labels)}. "
            f"Please clarify which applies to your situation:\n"
            + "\n".join(f"  - {label}" for label in labels)
        ),
    }


def _parse_title_from_excerpt(excerpt: str) -> str:
    """Extract section title from normalized text excerpt.
    Looks for 'Title: § 1926.502 Fall protection systems criteria and practices.'
    """
    import re as _re
    m = _re.search(r"Title:\s*(.+?)(?:\r|\n|Section:)", excerpt)
    if m:
        return m.group(1).strip()
    return ""


def _parse_section_from_source(source: str) -> str:
    """
    Extract a section ID from the S3 URI or source string.
    Handles both formats:
      s3://bucket/normalized/29_CFR_1926_451.txt -> "1926.451"
      s3://bucket/osha-docs/1910.178.txt         -> "1910.178"
    """
    if not source:
        return ""
    filename = source.rstrip("/").split("/")[-1]
    filename = filename.replace(".txt", "").replace(".json", "")
    if filename.startswith("29_CFR_"):
        rest = filename[len("29_CFR_"):] 
        return rest.replace("_", ".", 1)   
    import re as _re
    m = _re.match(r"^(1[89]\d{2})_(.+)$", filename)
    if m:
        return f"{m.group(1)}.{m.group(2).replace('_', '.')}"
    return filename


def discover(query: str, part_filter: str | None = None) -> dict:
    """Query Bedrock KB and return structured ranked results."""
    top_k = settings.BEDROCK_RETRIEVAL_TOP_K  # 10

    hits = bedrock_kb.retrieve(query, top_k=top_k)

    if not hits:
        raise OshaNoResultsError(f"No results found for query: {query!r}")
    
    for hit in hits:
        hit["section"] = _parse_section_from_source(hit["source"])

    logger.debug("[SEARCH] Sample sources: %s", [h["source"] for h in hits[:3]])
    logger.debug("[SEARCH] Sample sections: %s", [h["section"] for h in hits[:3]])

    if part_filter:
        hits = [h for h in hits if get_cfr_part(h["section"]) == part_filter]

    if not hits:
        raise OshaNoResultsError(f"No results found for query: {query!r} in part {part_filter}")

    # deduplicate by section, keep highest score per section
    seen = {}
    for hit in hits:
        sec = hit["section"] or hit["source"]
        if sec not in seen or hit["score"] > seen[sec]["score"]:
            seen[sec] = hit

    deduped = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    # normalize  0-100 
    max_score = deduped[0]["score"] if deduped else 1.0
    results = []
    for hit in deduped:
        section = hit["section"]
        part = get_cfr_part(section) or ""
        # normalized = min(int((hit["score"] / max_score) * 100), 100) if max_score else 0
        normalized = hit["score"]
        results.append({
            "section":    section,
            "source":     hit["source"],
            "title":      _parse_title_from_excerpt(hit["text"]) or REGULATORY_PARTS.get(part, section),
            "part":       part,
            "part_label": REGULATORY_PARTS.get(part, ""),
            "excerpt":    hit["text"],
            "score":      normalized,
        })

    ambiguity = _detect_ambiguity(results)
    if part_filter is None and ambiguity:
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
    """Search OSHA regulations to find relevant sections.

    Returns up to 10 ranked results. Each result includes:
    - section: OSHA section ID (e.g. "1910.178")
    - title: regulation title
    - source: S3 source URI
    - excerpt: relevant text snippet
    - score: relevance score 0-100 (100 = best match)

    When results span multiple parts (e.g. 1910 AND 1926), output will flag
    ambiguity so you can ask the user which industry applies.

    Args:
        query: Keywords describing the safety topic, hazard, or situation.
               Include workplace context when known.
               Good: "forklift operator training requirements warehouse"
               Good: "scaffolding fall protection construction"
               Too vague: "safety training"
        part_filter: Optional CFR part number to restrict scope.
                     Use when industry is already known.
                     Examples: "1910" (General Industry), "1926" (Construction)
    """
    try:
        result = discover(query, part_filter=part_filter)
    except OshaNoResultsError:
        filter_note = f" in Part {part_filter}" if part_filter else ""
        return json.dumps({
            "type":    "search_no_results",
            "query":   query,
            "message": f"No results found for '{query}'{filter_note}. Try different keywords.",
        })

    items = []
    for r in result["results"]:
        items.append({
            "section":    r["section"],
            "title":      r.get("title", ""),
            "osha_url":   _build_osha_url(r["section"]),
            "part":       r.get("part", ""),
            "part_label": r.get("part_label", ""),
            "score":      r["score"],
            "excerpt":    r["excerpt"][:500],
        })

    return json.dumps({
        "type":          "search_results",
        "query":         query,
        "ambiguous":     result.get("ambiguous", False),
        "clarification": result.get("clarification"),
        "results":       items,
    })
