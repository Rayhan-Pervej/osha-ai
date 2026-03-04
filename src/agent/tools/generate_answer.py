import logging
import re

from langchain_core.tools import tool

from src.llm import bedrock
from src.retrieval.bm25 import get_raw_content, get_section_metadata, get_top_chunks
from src.exceptions.errors import OshaDocumentNotFoundError, OshaGenerationError

logger = logging.getLogger(__name__)


_MAX_CONTEXT_CHARS = 20_000

GENERATION_PROMPT = """You are an OSHA compliance assistant.
You answer using ONLY the regulatory text provided below. Do NOT use any outside knowledge.

ANSWER FORMAT — always follow this exact structure:

PART 1 — PLAIN LANGUAGE SUMMARY (required first):
In 3-6 sentences, explain what the regulation requires in plain language for a non-expert worker or manager.
- Use ONLY information from the source text. Do NOT add facts from memory.
- Write in clear, simple language. No legal jargon.
- Focus on what the employer/employee must DO, by WHEN, and any specific numbers or deadlines.
- Start this section with: "What you need to know:"

PART 2 — SOURCE REGULATIONS (required after summary):
Start this section with the header: "#### 📋 Source Regulations"
List every sentence from the source text that directly supports the summary above.
Format each quote as:
  > [Section X.XXX] "exact sentence word-for-word from the source"

Rules for quoting — STRICT, never break these:
- COPY THE SENTENCE EXACTLY AS IT APPEARS IN THE SOURCE. Character for character. No changes whatsoever.
- Do NOT paraphrase, summarize, trim, reorder words, change punctuation, or add/remove any word.
- Do NOT capitalize, lowercase, or alter any word to make it fit your sentence.
- Always quote from the START of the sentence. Never begin mid-sentence.
- If a sentence begins with "Except...", "Unless...", "When...", "Subject to..." — include the full sentence from the beginning. These are legal conditions that change the meaning if dropped.
- If you cannot find a relevant sentence that you can quote exactly, do NOT quote anything — write: NOT FOUND IN SOURCE.
- Prefer specific rules (measurements, deadlines, requirements) over general/scope paragraphs.
- Include ALL relevant sub-paragraphs — do not stop at the general rule.

NOT FOUND — when the text does not contain the answer:
- Write: NOT FOUND IN SOURCE
- Use this when the text only cross-references another section or has no actual rules.
- Do NOT guess. Do NOT infer from general OSHA principles.

Return a single valid JSON object. No markdown fences. No text outside the JSON.

{
  "answer": "<PART 1 plain language summary + PART 2 source regulations, or NOT FOUND IN SOURCE>",
  "sections_cited": ["<section_id>"],
  "verbatim_quotes": ["<EXACT character-for-character copy from source — no changes allowed>"],
  "disclaimer": "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA."
}"""


def _normalize(text: str) -> str:
    """Normalize text — collapse whitespace, fix encoding."""
    text = text.replace("\u00a7", "\u00a7").replace("\ufffd", "\u00a7")
    text = re.sub(r"\s+", " ", text).strip()
    return text





def _calculate_display_score(answer: dict, raw_content: str, context_relevance: float) -> dict:
    """Compute two genuinely different scores:

    - verbatim_pct:   % of extracted quotes verified word-for-word in source
                      (quote verification: did the LLM quote real sentences?)

    - confidence_pct: mean BM25 relevance of retrieved chunks to the query
                      (context relevance: was the right content retrieved?)
                      Capped at 95 to avoid overconfidence.
    """
    raw_answer = answer.get("answer", "")

    if "NOT FOUND IN SOURCE" in raw_answer:
        answer["confidence_pct"] = 0
        answer["verbatim_pct"] = 0
        return answer

    # Verbatim: what % of extracted quotes are verified real in the source
    norm_source = _normalize(raw_content)
    verbatim_quotes = answer.get("verbatim_quotes", []) or []
    if verbatim_quotes:
        verified = sum(
            1 for q in verbatim_quotes
            if q.strip() and _normalize(q).lower() in norm_source.lower()
        )
        verbatim_pct = int((verified / len(verbatim_quotes)) * 100)
    else:
        verbatim_pct = 0

    # Confidence: mean BM25 relevance of retrieved context to the query
    confidence_pct = min(int(context_relevance * 100), 95)

    # Deduplicate section citations
    if answer.get("sections_cited"):
        answer["sections_cited"] = list(dict.fromkeys(
            re.sub(r"\([0-9]+\)", "", s).strip()
            for s in answer["sections_cited"]
        ))

    answer["confidence_pct"] = confidence_pct
    answer["verbatim_pct"] = verbatim_pct

    return answer

@tool
def generate_answer(section_id: str, query: str) -> str:
    """Generate a verified compliance answer from a specific OSHA section.

    Reads the section's full regulatory text, selects the most relevant
    portions, sends them to the LLM for answer generation, then verifies
    every quoted sentence against the original source text for accuracy.

    Returns the answer text along with verification scores and source quotes.

    IMPORTANT: Write a detailed, specific query — not just the user's raw words.
    Good:  "What fall protection is required for each type of scaffold above 10 feet?"
    Bad:   "scaffolding"

    Args:
        section_id: The exact OSHA section ID to generate an answer from.
                    Must match a section in the database exactly.
                    Examples: "1926.451", "1910.1030", "1910.178", "FOM-chapter-4"
        query: A detailed question to answer from this section's text.
               Be specific about what the user wants to know — include the
               hazard type, situation, and what kind of requirements they need.
    """
    try:
        section_meta = get_section_metadata(section_id)
    except OshaDocumentNotFoundError:
        return f"Section '{section_id}' not found in the database. Use search_regulations to find valid section IDs."


    try:
        context_text, context_relevance = get_top_chunks(section_id, query, _MAX_CONTEXT_CHARS)
    except OshaDocumentNotFoundError:
        return f"No text content found for section '{section_id}'."

    try:
        full_text = get_raw_content(section_id)
    except OshaDocumentNotFoundError:
        full_text = context_text

    user_message = (
        f"LOCKED REGULATORY TEXT:\n"
        f"[Section: {section_id}]\n"
        f"Source: {section_meta.get('source', '')}\n"
        f"Title: {section_meta.get('title', '')}\n"
        f"Path: {section_meta.get('path', '')}\n"
        f"Text:\n{context_text}\n\n"
        f"USER QUESTION:\n{query}"
    )

    try:
        answer = bedrock.invoke(GENERATION_PROMPT, user_message)
    except OshaGenerationError as e:
        return f"Answer generation failed: {e}"

    answer = _calculate_display_score(answer, full_text, context_relevance)

    result_parts = [answer.get("answer", "No answer generated.")]

    result_parts.append(f"\n\n---\nSection used: {section_id}")
    result_parts.append(f"Confidence: {answer.get('confidence_pct', 0)}%")
    result_parts.append(f"Verbatim: {answer.get('verbatim_pct', 0)}%")

    if answer.get("disclaimer"):
        result_parts.append(f"\n{answer['disclaimer']}")

    return "\n".join(result_parts)
