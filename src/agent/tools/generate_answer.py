import logging
import re

from langchain_core.tools import tool

from src.llm import bedrock
from src.retrieval.bm25 import get_raw_content, get_section_metadata, get_top_chunks
from src.exceptions.errors import OshaDocumentNotFoundError, OshaGenerationError

logger = logging.getLogger(__name__)


_MAX_CONTEXT_CHARS = 14_000

GENERATION_PROMPT = """You are an OSHA compliance assistant.
You answer using ONLY the regulatory text provided below. Do NOT use any outside knowledge — not from training, not from memory. If the answer is not in the text below, say NOT FOUND IN SOURCE.

ANSWERING RULES — follow in strict order:

1. VERBATIM MATCH (preferred):
   Find the exact sentence(s) in the text that directly answer the question.
   Copy them word-for-word into your answer and into verbatim_quotes.
   Prefer specific rules (measurements, deadlines, explicit requirements) over
   general introductory paragraphs.
   If a section has sub-paragraphs (a), (b), (c)... with specific rules, use
   those instead of the general "(a) Scope" or "(a) General" paragraph.
   Set verbatim_score close to 1.0.

2. CONTEXT-BASED ANSWER (when no single verbatim sentence suffices):
   If the answer requires combining facts from multiple paragraphs, construct
   a faithful summary using ONLY terms and facts from the source text.
   Do NOT add any detail that does not appear word-for-word in the source.
   Set verbatim_score between 0.3 and 0.7. Set confidence to "Partial match".

3. NOT FOUND (when the text does not contain the answer):
   Use "NOT FOUND IN SOURCE" when:
   - The text only cross-references another section (e.g. "see subpart L", "see §1926.501")
   - The text only states scope or applicability with no actual rules
   - The specific requirement asked about is not present in the provided text
   Do NOT guess. Do NOT use outside knowledge. Do NOT infer from general OSHA principles.

4. CONVERSATION REFERENCE:
   If the question is about the conversation itself (e.g. "what did I ask?"),
   answer from conversation context. Do NOT say NOT FOUND for these.

HALLUCINATION PREVENTION — critical:
- Every fact in your answer must be traceable to a specific sentence in the source text.
- If you cannot quote it verbatim, do not state it as fact.
- Numbers, heights, distances, percentages — only state them if they appear exactly in the source.
- Do NOT extrapolate. "The text implies..." or "Generally, OSHA requires..." are not acceptable.

Cross-references that do NOT count as answers:
  - "Requirements are provided in subpart L of this part." → NOT FOUND IN SOURCE
  - "See §1926.501 for fall protection requirements." → NOT FOUND IN SOURCE

IMPORTANT: Include ALL relevant sub-paragraphs in your answer. If the source has
specific requirements for different types (scaffold types, chemical types, etc.),
list them all rather than giving only the general rule.

Return a single valid JSON object. No markdown fences. No text outside the JSON.

{
  "answer": "<verbatim text, faithful summary from source, or NOT FOUND IN SOURCE>",
  "sections_cited": ["<section_id>"],
  "verbatim_quotes": ["<exact word-for-word sentence(s) from the source text>"],
  "confidence": "<Exact match | Partial match | Keyword match only>",
  "confidence_score": 0.95,
  "verbatim_score": 1.0,
  "disclaimer": "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA."
}"""


def _normalize(text: str) -> str:
    """Normalize text for quote comparison — collapse whitespace, fix encoding."""
    text = text.replace("\u00a7", "\u00a7").replace("\ufffd", "\u00a7")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _calculate_display_score(answer: dict, raw_content: str) -> dict:
    """Score the answer by verifying quoted text against the original source."""
    raw_answer = answer.get("answer", "")
    verbatim_quotes = answer.get("verbatim_quotes", []) or []
    confidence = answer.get("confidence", "")

    if "NOT FOUND IN SOURCE" in raw_answer:
        answer["display_pct"] = 0
        answer["display_label"] = "Not Found"
        answer["quote_verification_pct"] = 0
        answer["verbatim_coverage_pct"] = 0
        return answer

    norm_source = _normalize(raw_content)

    if verbatim_quotes:
        verified = sum(
            1 for q in verbatim_quotes
            if q.strip() and _normalize(q) in norm_source
        )
        quote_verification_pct = int((verified / len(verbatim_quotes)) * 100)
    else:
        quote_verification_pct = 0

    if verbatim_quotes and raw_answer:
        quote_chars = sum(
            len(q) for q in verbatim_quotes
            if q.strip() and _normalize(q) in norm_source
        )
        answer_chars = len(raw_answer)
        verbatim_coverage_pct = int(min(quote_chars / answer_chars, 1.0) * 100)
    else:
        verbatim_coverage_pct = 0
    if confidence == "Exact match":
        label = "Exact Match"
    elif confidence == "Partial match":
        label = "Partial Match"
    else:
        label = "Keyword Match"

    display_pct = quote_verification_pct if quote_verification_pct > 0 else verbatim_coverage_pct

    # Deduplicate section citations
    if answer.get("sections_cited"):
        answer["sections_cited"] = list(dict.fromkeys(
            re.sub(r"\([0-9]+\)", "", s).strip()
            for s in answer["sections_cited"]
        ))

    answer["display_pct"] = display_pct
    answer["display_label"] = label
    answer["quote_verification_pct"] = quote_verification_pct
    answer["verbatim_coverage_pct"] = verbatim_coverage_pct

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
        context_text = get_top_chunks(section_id, query, _MAX_CONTEXT_CHARS)
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

    answer = _calculate_display_score(answer, full_text)

    result_parts = [answer.get("answer", "No answer generated.")]

    result_parts.append(f"\n\n---\nSection used: {section_id}")
    result_parts.append(f"Quote verification: {answer.get('quote_verification_pct', 0)}%")
    result_parts.append(f"Verbatim coverage: {answer.get('verbatim_coverage_pct', 0)}%")
    result_parts.append(f"Confidence: {answer.get('confidence', 'unknown')}")

    if answer.get("verbatim_quotes"):
        result_parts.append("\nVerbatim quotes from source:")
        for q in answer["verbatim_quotes"]:
            result_parts.append(f"> {q}")

    if answer.get("disclaimer"):
        result_parts.append(f"\n{answer['disclaimer']}")

    return "\n".join(result_parts)
