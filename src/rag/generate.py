import logging

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

    context = _build_context(locked_sections, query)
    user_message = f"LOCKED REGULATORY TEXT:\n{context}\n\nUSER QUESTION:\n{query}"

    answer = bedrock.invoke(SYSTEM_PROMPT, user_message, history=history)

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


def _build_context(locked_sections: list[dict], query: str) -> str:
    n = len(locked_sections)
    budget_per_section = _MAX_CONTEXT_CHARS // n

    parts = []
    for s in locked_sections:
        section_id = s.get("section_id", "")

        try:
            raw = get_top_chunks(section_id, query, budget_per_section)
        except OshaDocumentNotFoundError:
            raw = s.get("excerpt", "")

        parts.append(
            f"[Section: {section_id}]\n"
            f"Source: {s.get('source', '')}\n"
            f"Title: {s.get('title', '')}\n"
            f"Path: {s.get('path', '')}\n"
            f"Text:\n{raw}"
        )
    return "\n\n---\n\n".join(parts)
