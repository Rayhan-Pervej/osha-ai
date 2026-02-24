import logging

from src.exceptions.errors import OshaDocumentNotFoundError
from src.llm import bedrock
from src.rag.prompts import SYSTEM_PROMPT
from src.retrieval.bm25 import get_raw_content
from src.utils.extract_relevant_texts import extract_relevant_window

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
    parts = []
    for s in locked_sections:
        section_id = s.get("section_id", "")
        local_path = s.get("local_path", "")

        if local_path:
            try:
                with open(local_path, encoding="utf-8") as f:
                    text = f.read()
                excerpt = extract_relevant_window(text, query, max_chars=10000)
            except Exception as e:
                logger.warning(f"Could not read file {local_path}: {e}")
                try:
                    raw = get_raw_content(section_id)
                    excerpt = extract_relevant_window(raw, query, max_chars=10000)
                except OshaDocumentNotFoundError:
                    excerpt = s.get("excerpt", "")
        else:
            try:
                raw = get_raw_content(section_id)
                excerpt = extract_relevant_window(raw, query, max_chars=10000)
            except OshaDocumentNotFoundError:
                excerpt = s.get("excerpt", "")

        parts.append(
            f"[Section: {section_id}]\n"
            f"Source: {s.get('source', '')}\n"
            f"Title: {s.get('title', '')}\n"
            f"Path: {s.get('path', '')}\n"
            f"Text:\n{excerpt}"
        )
    return "\n\n---\n\n".join(parts)
