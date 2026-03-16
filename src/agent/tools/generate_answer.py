import re
import json
import logging
from langchain_core.tools import tool

from src.llm import bedrock
from src.retrieval import bedrock_kb
from src.config import settings
from src.exceptions.errors import OshaGenerationError
from src.agent.prompts.generation import GENERATION_PROMPT

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    text = text.replace("\u00a7", "§").replace("\ufffd", "§")
    # normalize curly/smart quotes to straight quotes
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    # normalize em/en dash variants to em dash
    text = text.replace("\u2013", "\u2014").replace(" - ", "\u2014")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:!?)'\]])", r"\1", text)
    return text


def _build_osha_url(section: str) -> str:
    # FOM chapter-specific URLs: "Chapter 4 Violations" -> https://www.osha.gov/fom/chapter-4
    if "Chapter" in section:
        m = re.match(r"Chapter\s+(\d+)", section)
        if m:
            return f"https://www.osha.gov/fom/chapter-{m.group(1)}"
        return "https://www.osha.gov/fom"
    if "Field Operations Manual" in section:
        return "https://www.osha.gov/fom"
    # OSHA Act
    if "osha-act" in section.lower() or "osh act" in section.lower():
        return "https://www.osha.gov/laws-regs/oshact/completeoshact"
    # Standard CFR section number e.g. 1926.502
    m = re.match(r"^(\d{4})(\..*)?$", section)
    if not m:
        return ""
    part = m.group(1)
    return f"https://www.osha.gov/laws-regs/regulations/standardnumber/{part}/{section}"


def _format_citation_label(section: str) -> str:
    if re.match(r"^\d{4}", section):
        return f"29 CFR §{section}"
    return section


def _build_references(sections: list[str]) -> list[dict]:
    return [
        {"section": _format_citation_label(s.strip()), "url": _build_osha_url(s.strip())}
        for s in sections
    ]


def _calculate_scores(body: str, context_text: str, hits: list[dict]) -> tuple[int, int, list[dict]]:
    norm_source = _normalize(context_text).lower()
    # extract quotes from blockquote lines: > "quote text" — citation
    spans = re.findall(r'^>\s*[\u201c"](.+?)[\u201d"]', body, re.MULTILINE)

    verified_quotes = []
    if spans:
        for span in spans:
            found = _normalize(span).lower() in norm_source
            verified_quotes.append({"quote": span.strip(), "found_in_source": found})
        verified_count = sum(1 for q in verified_quotes if q["found_in_source"])
        verbatim_pct = int((verified_count / len(spans)) * 100)
    else:
        verbatim_pct = 0

    if hits:
        top_scores = sorted([h.get("score", 0.0) for h in hits], reverse=True)[:3]
        retrieval_score = int((sum(top_scores) / len(top_scores)) * 100) if top_scores else 0
    else:
        retrieval_score = 0

    confidence = int(0.70 * verbatim_pct + 0.30 * retrieval_score)
    return confidence, verbatim_pct, verified_quotes


@tool
def generate_answer(sections: list[str], query: str) -> str:
    """Generate a source-verified compliance answer from one or more OSHA sections.

    Args:
        sections: List of section IDs from search_regulations (e.g. ["1910.178"] or ["1910.178", "1926.451"]).
        query: The user's question.
    """
    section_label = ", ".join(sections)

    hits = bedrock_kb.retrieve_for_section(query, sections, top_k=settings.BEDROCK_RETRIEVAL_TOP_K)

    if not hits:
        return json.dumps({
            "type":               "generate_result",
            "title":              section_label,
            "body":               "NOT FOUND IN SOURCE",
            "references":         _build_references(sections),
            "verbatim_quotes":    [],
            "confidence_percent": 0,
            "verbatim_percent":   0,
            "not_found":          True,
            "disclaimer":         "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA.",
        })

    context_text = "\n\n".join(h["text"] for h in hits)
    source_uris  = list(dict.fromkeys(h.get("source", "") for h in hits if h.get("source")))
    source_uri   = source_uris[0] if source_uris else ""

    user_message = (
        f"LOCKED REGULATORY TEXT:\n"
        f"Section: {section_label}\n"
        f"Source: {source_uri}\n\n"
        f"Text:\n{context_text}\n\n"
        f"USER QUESTION:\n{query}"
    )

    try:
        answer = bedrock.invoke(GENERATION_PROMPT, user_message)
    except OshaGenerationError as e:
        return json.dumps({
            "type": "generate_result", "title": section_label,
            "body": f"Answer generation failed: {e}",
            "references": _build_references(sections),
            "verbatim_quotes": [], "confidence_percent": 0,
            "verbatim_percent": 0, "not_found": True, "disclaimer": "",
        })

    body = answer.get("body", "")
    title = answer.get("title", section_label)
    confidence, verbatim_pct, verified_quotes = _calculate_scores(body, context_text, hits)

    return json.dumps({
        "type":               "generate_result",
        "title":              title,
        "body":               body.strip(),
        "references":         _build_references(sections),
        "verbatim_quotes":    verified_quotes,
        "confidence_percent": confidence,
        "verbatim_percent":   verbatim_pct,
        "not_found":          body.strip() == "NOT FOUND IN SOURCE",
        "source_uris":        source_uris,
        "source_uri":         source_uri,
        "disclaimer":         "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA.",
    })

