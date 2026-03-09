import re
import json
import logging
from langchain_core.tools import tool

from src.llm import bedrock
from src.retrieval import bedrock_kb
from src.config import settings
from src.exceptions.errors import OshaGenerationError

logger = logging.getLogger(__name__)

GENERATION_PROMPT = """You are an OSHA compliance assistant.
You answer using ONLY the locked regulatory text provided below. Do NOT use any outside knowledge.

RULES:
- summary: One professional sentence summarizing the regulation.
- bullets: 2-7 bullets. Each bullet MUST be copied EXACTLY word-for-word from the source text — including all parenthetical text, all sub-clauses, and the complete sentence without cutting it short. Only include bullets where you have the exact text in front of you.
- why: Brief explanation of why these requirements prevent injuries. Must be supported by the source text.
- disclaimer: Always use exactly: "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA."
- If no relevant information found, set summary to "NOT FOUND IN SOURCE" and bullets to empty list.
- Do NOT infer or guess from general OSHA principles. Use ONLY the locked text."""


def _normalize(text: str) -> str:
    text = text.replace("\u00a7", "§").replace("\ufffd", "§")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_osha_url(section: str) -> str:
    m = re.match(r"^(\d{4})(\..*)?$", section)
    if not m:
        return ""
    part = m.group(1)
    return f"https://www.osha.gov/laws-regs/regulations/standardnumber/{part}/{section}"


def _build_manager_citations(answer: dict, section: str) -> list[dict]:
    seen = set()
    citations = []
    primary_label = f"29 CFR §{section}"
    seen.add(section)
    citations.append({"section": primary_label, "url": _build_osha_url(section)})
    for bullet in answer.get("bullets", []):
        for cite_str in bullet.get("citations", []):
            m = re.search(r"§(\d{4}\.\d+)", cite_str)
            if m:
                sec_id = m.group(1)
                if sec_id not in seen:
                    seen.add(sec_id)
                    citations.append({"section": f"29 CFR §{sec_id}", "url": _build_osha_url(sec_id)})
    return citations


def _calculate_scores(answer: dict, context_text: str, hits: list[dict]) -> dict:
    """
    confidence_percent (0-100): weighted combination of verbatim accuracy + retrieval quality.
    verbatim_percent   (0-100): % of bullet text verified word-for-word in source.
    Both 0 when NOT FOUND IN SOURCE.
    """
    if "NOT FOUND IN SOURCE" in answer.get("summary", ""):
        answer["confidence_percent"] = 0
        answer["verbatim_percent"] = 0
        return answer

    norm_source = _normalize(context_text)
    bullets = answer.get("bullets", [])

    if bullets:
        verified = 0
        for b in bullets:
            text = _normalize(b.get("text", "")).lower()
            if not text:
                continue
            # Split into sentences and check each one — bullets may span multiple sentences
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 20]
            if sentences and any(s in norm_source.lower() for s in sentences):
                verified += 1
        verbatim_pct = int((verified / len(bullets)) * 100)
    else:
        verbatim_pct = 0

    # retrieval score: mean of top-3 chunk scores, normalized to 0-100
    if hits:
        top_scores = sorted([h.get("score", 0.0) for h in hits], reverse=True)[:3]
        retrieval_score = int((sum(top_scores) / len(top_scores)) * 100)
    else:
        retrieval_score = 0

    answer["confidence_percent"] = int(0.70 * verbatim_pct + 0.30 * retrieval_score)
    answer["verbatim_percent"] = verbatim_pct
    return answer


@tool
def generate_answer(section: str, query: str) -> str:
    """Generate a source-verified compliance answer from a locked OSHA section.

    Retrieves the full text of the selected section from the knowledge base,
    sends it to the LLM with the user's question, and verifies every quoted
    sentence against the original source text.

    Returns a JSON string with:
    - answer: plain language summary + verbatim source quotes
    - citations: list of {section_id, quote} verified against source
    - sections_cited: list of section IDs referenced
    - confidence_pct: 0-100, weighted score of verbatim accuracy + retrieval quality
    - verbatim_pct: 0-100, % of quotes found word-for-word in source
    - section: the locked section ID
    - source_uri: S3 URI of the source document
    - disclaimer: standard legal disclaimer

    Args:
        section: The section ID from search_regulations results (e.g. "1910.178").
        query: Detailed question capturing everything the user needs.
               Good: "What forklift operator training is required, including frequency and documentation?"
               Bad:  "forklift training"
    """
    hits = bedrock_kb.retrieve_for_section(query, section, top_k=10)

    if not hits:
        return json.dumps({
            "type": "generate_result",
            "summary": "NOT FOUND IN SOURCE",
            "bullets": [],
            "why": "",
            "confidence_percent": 0,
            "verbatim_percent": 0,
            "manager_citations": [{"section": f"29 CFR §{section}", "url": _build_osha_url(section)}],
            "section": section,
            "source_uri": "",
            "disclaimer": "",
        })

    context_text = "\n\n".join(h["text"] for h in hits)
    source_uri = hits[0].get("source", "")

    user_message = (
        f"LOCKED REGULATORY TEXT:\n"
        f"Section: {section}\n"
        f"Source: {source_uri}\n\n"
        f"Text:\n{context_text}\n\n"
        f"USER QUESTION:\n{query}"
    )

    try:
        answer = bedrock.invoke(GENERATION_PROMPT, user_message)
    except OshaGenerationError as e:
        return json.dumps({"type": "generate_result", "summary": f"Answer generation failed: {e}",
                           "bullets": [], "why": "", "confidence_percent": 0,
                           "verbatim_percent": 0, "section": section, "source_uri": source_uri, "disclaimer": ""})

    answer = _calculate_scores(answer, context_text, hits)
    answer["manager_citations"] = _build_manager_citations(answer, section)
    answer["type"] = "generate_result"
    answer["section"] = section
    answer["source_uri"] = source_uri
    return json.dumps(answer)


