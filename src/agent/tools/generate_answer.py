import re
import logging
from langchain_core.tools import tool

from src.llm import bedrock
from src.retrieval import bedrock_kb
from src.config import settings
from src.exceptions.errors import OshaGenerationError

logger = logging.getLogger(__name__)

GENERATION_PROMPT = """You are an OSHA compliance assistant.
You answer using ONLY the locked regulatory text provided below. Do NOT use any outside knowledge.

ANSWER FORMAT — always follow this exact structure:

PART 1 — PLAIN LANGUAGE SUMMARY (required):
In 3-6 sentences, explain what the regulation requires in plain language.
- Use ONLY information from the locked text. Do NOT add facts from memory.
- Write clearly for a non-expert worker or manager. No legal jargon.
- Focus on what the employer/employee must DO, by WHEN, and any specific numbers or deadlines.
- Start with: "What you need to know:"

PART 2 — VERBATIM SOURCE TEXT (required):
Header: "#### Source Regulations"
List every sentence from the locked text that directly supports the summary.
Format:
  > [Section X.XXX] "exact sentence copied word-for-word from the source"

Quoting rules — STRICT:
- Copy sentences EXACTLY as they appear. No paraphrasing, trimming, or rewording.
- Quote from the START of the sentence. Never begin mid-sentence.
- Include conditional sentences in full ("Except...", "Unless...", "When...").
- When a numbered item contains multiple sentences that together form one rule (e.g. "You must do X by deadline A. For Y, the deadline is B."), quote ALL sentences from that item as one entry — do not stop at the first sentence.
- If no exact sentence supports the answer, write: NOT FOUND IN SOURCE.
- Prefer specific rules (numbers, deadlines, requirements) over general scope text.

NOT FOUND:
- Write: NOT FOUND IN SOURCE
- Do NOT infer or guess from general OSHA principles.

Return a single valid JSON object. No markdown fences. No text outside the JSON.

{
  "answer": "<PART 1 summary + PART 2 verbatim source, or NOT FOUND IN SOURCE>",
  "sections_cited": ["<exact section ID from the text>"],
  "verbatim_quotes": ["<exact word-for-word copy — no changes>"],
  "disclaimer": "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA."
}"""


def _normalize(text: str) -> str:
    text = text.replace("\u00a7", "§").replace("\ufffd", "§")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _calculate_scores(answer: dict, context_text: str, hits: list[dict]) -> dict:
    """
    confidence_pct (0-100): weighted combination of faithfulness + retrieval quality.
    verbatim_pct   (0-100): % of LLM quotes verified word-for-word in source.
    Both 0 when NOT FOUND IN SOURCE.

    confidence_pct = int(0.70 * verbatim_pct + 0.30 * retrieval_score)


    """
    if "NOT FOUND IN SOURCE" in answer.get("answer", ""):
        answer["confidence_pct"] = 0
        answer["verbatim_pct"] = 0
        return answer

    #  verbatim score
    norm_source = _normalize(context_text)
    quotes = answer.get("verbatim_quotes", []) or []

    if quotes:
        verified = sum(
            1 for q in quotes
            if q.strip() and _normalize(q).lower() in norm_source.lower()
        )
        verbatim_pct = int((verified / len(quotes)) * 100)
    else:
        verbatim_pct = 0

    # retrieval score: mean of top-3 chunk scores, normalized to 0-100
    if hits:
        top_scores = sorted([h.get("score", 0.0) for h in hits], reverse=True)[:3]
        retrieval_score = int((sum(top_scores) / len(top_scores)) * 100)
    else:
        retrieval_score = 0


    confidence_pct = int(0.70 * verbatim_pct + 0.30 * retrieval_score)

    if answer.get("sections_cited"):
        answer["sections_cited"] = list(dict.fromkeys(
            re.sub(r"\([0-9]+\)", "", s).strip()
            for s in answer["sections_cited"]
        ))

    answer["confidence_pct"] = confidence_pct
    answer["verbatim_pct"] = verbatim_pct
    return answer

@tool
def generate_answer(section: str, query: str) -> str:
    """Generate a source-verified compliance answer from a locked OSHA section.

    Retrieves the full text of the selected section from the knowledge base,
    sends it to the LLM with the user's question, and verifies every quoted
    sentence against the original source text.

    Returns:
    - Plain language summary of what the regulation requires
    - Verbatim source quotes with section citations
    - Source link
    - Confidence score (0-95): how well quotes are verified
    - Verbatim score (0-100): % of quotes found word-for-word in source

    Args:
        section: The section ID from search_regulations results (e.g. "1910.178").
        query: Detailed question capturing everything the user needs.
               Good: "What forklift operator training is required, including frequency and documentation?"
               Bad:  "forklift training"
    """
    hits = bedrock_kb.retrieve_for_section(query, section, top_k=10)

    if not hits:
        return f"No content found for section '{section}'. Use search_regulations to find valid sections."

    context_text = "\n\n".join(h["text"] for h in hits)
    source_uri = hits[0].get("source", "")

    verification_text = context_text

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
        return f"Answer generation failed: {e}"

    answer = _calculate_scores(answer, verification_text, hits)

    lines = [answer.get("answer", "No answer generated.")]
    lines.append("\n---")
    lines.append(f"Section: {section}")
    if source_uri:
        lines.append(f"Source: {source_uri}")
    lines.append(f"Confidence: {answer.get('confidence_pct', 0)}%")
    lines.append(f"Verbatim: {answer.get('verbatim_pct', 0)}%")
    if answer.get("disclaimer"):
        lines.append(f"\n{answer['disclaimer']}")

    return "\n".join(lines)
