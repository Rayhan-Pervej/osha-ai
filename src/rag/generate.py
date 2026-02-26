import logging
import re
from src.exceptions.errors import OshaDocumentNotFoundError
from src.llm import bedrock
from src.rag.prompts import SYSTEM_PROMPT
from src.retrieval.bm25 import get_top_chunks

# ~14 000 chars ≈ 4 000 tokens of regulatory text
_MAX_CONTEXT_CHARS = 14000

logger = logging.getLogger(__name__)


def generate(query: str, locked_sections: list[dict], history: list[dict] | None = None) -> dict:
    if not locked_sections:
        raise ValueError("No locked sections provided. Run search first and lock section IDs.")

    context, raw_content = _build_context(locked_sections, query)
    user_message = f"LOCKED REGULATORY TEXT:\n{context}\n\nUSER QUESTION:\n{query}"

    answer = bedrock.invoke(SYSTEM_PROMPT, user_message, history=history)
    answer = _calculate_display_score(answer, raw_content)

    return {
        "query": query,
        "locked_section_ids": [s.get("section_id") for s in locked_sections],
        "answer": answer,
        "generation_invoked": True,
        "history": (history or []) + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": answer.get("answer", "")},
        ],
    }


def _build_context(locked_sections: list[dict], query: str) -> tuple[str, str]:
    """Build context string and return raw_content for score verification."""
    n = len(locked_sections)
    budget_per_section = _MAX_CONTEXT_CHARS // n

    parts = []
    raw_parts = []
    for s in locked_sections:
        section_id = s.get("section_id", "")

        try:
            raw = get_top_chunks(section_id, query, budget_per_section)
        except OshaDocumentNotFoundError:
            raw = s.get("excerpt", "")

        raw_parts.append(raw)
        parts.append(
            f"[Section: {section_id}]\n"
            f"Source: {s.get('source', '')}\n"
            f"Title: {s.get('title', '')}\n"
            f"Path: {s.get('path', '')}\n"
            f"Text:\n{raw}"
        )

    return "\n\n---\n\n".join(parts), "\n\n".join(raw_parts)


def _calculate_display_score(answer: dict, raw_content: str) -> dict:
    """Calculate objective display scores from the LLM answer and source text."""
    raw_answer      = answer.get("answer", "")
    verbatim_quotes = answer.get("verbatim_quotes", []) or []
    confidence      = answer.get("confidence", "")

    
    if "NOT FOUND IN SOURCE" in raw_answer:
        answer["display_pct"]           = 0
        answer["display_label"]         = "Not Found"
        answer["quote_verification_pct"] = 0
        answer["verbatim_coverage_pct"]  = 0
        return answer

    # Quote verification 
    if verbatim_quotes:
        verified = sum(1 for q in verbatim_quotes if q.strip() and q.strip() in raw_content)
        quote_verification_pct = int((verified / len(verbatim_quotes)) * 100)
    else:
        quote_verification_pct = 0

    # Verbatim coverage 
    if verbatim_quotes and raw_answer:
        quote_chars = sum(len(q) for q in verbatim_quotes if q.strip() in raw_content)
        answer_chars = len(raw_answer)
        verbatim_coverage_pct = int(min(quote_chars / answer_chars, 1.0) * 100)
    else:
        verbatim_coverage_pct = 0

    #  Display label from confidence string 
    if confidence == "Exact match":
        label = "Exact Match"
    elif confidence == "Partial match":
        label = "Partial Match"
    else:
        label = "Keyword Match"

    if quote_verification_pct > 0:
        display_pct = quote_verification_pct
    else:
        display_pct = verbatim_coverage_pct

    if answer.get("sections_cited"):
        answer["sections_cited"] = list(dict.fromkeys(
            re.sub(r'\([0-9]+\)', '', s).strip()
            for s in answer["sections_cited"]
        ))

    answer["display_pct"]            = display_pct
    answer["display_label"]          = label
    answer["quote_verification_pct"] = quote_verification_pct
    answer["verbatim_coverage_pct"]  = verbatim_coverage_pct

    return answer
