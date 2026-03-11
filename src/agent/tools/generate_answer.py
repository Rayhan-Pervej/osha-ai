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
Answer using ONLY the locked regulatory text provided. Do NOT use outside knowledge.

Your response must have exactly two fields:
- title: 3-6 words. Derive from the actual section heading in the source. Do NOT use the section number. Do NOT write generic phrases like "General Requirements" or "Overview".
- body: Answer the user's question using the structure that best fits. Embed every word-for-word quote in double curly braces {{exact quoted text}} and cite inline immediately after: {{quote}} per §1910.28(b)(1)(i). If no relevant information found, write exactly: NOT FOUND IN SOURCE

BODY FORMAT:
- Broad question (overview, summary, "tell me about"): use intro sentence + 2-4 bold headers for the main content + one conclusion sentence. Maximum 4 headers, 1-2 quotes per header. Pick the most important rules only.
- Specific question (single rule, definition, deadline, exemption, yes/no): answer directly in plain prose. No headers needed — just answer the question clearly and concisely with supporting verbatim quotes.
- Comparison (vs, difference between, two sections): one bold header per section being compared.

PROSE RULES:
- Never restate in verbatim what you already said in prose. Each point appears once — either as a {{verbatim quote}} or as plain prose, never both.
- Never open a sentence with a citation. Write the idea first, embed the quote, cite after.
  BAD:  Per §1910.28(b)(1)(i), Each employee on a walking-working surface...
  GOOD: The 4-foot rule applies to all elevated surfaces — {{each employee on a walking-working surface with an unprotected side or edge that is 4 feet (1.2 m) or more above a lower level is protected from falling by one or more of the following: (A) Guardrail systems; (B) Safety net systems; or (C) Personal fall protection systems}} per §1910.28(b)(1)(i).
- Keep verbatim quotes complete. Include all listed options (A)(B)(C) inside the {{...}}. Never split a quote and continue its list as separate bullets outside the braces.

CITATION RULES:
- Specific lookup: cite 2-5 sub-sections directly relevant
- Overview / summary: cite only the 3-4 most important sub-sections
- Checklist / audit: cite every distinct requirement, up to 7
- Comparison: cite 2-3 references per section being compared
- Exception / exemption: cite 1-3 targeted references
- Never cite a section you did not directly reference in the body
- Do NOT add any citation list, reference block, or §X.X list at the end of the body. Inline only.

STRICT RULES:
- Use ONLY the text provided. Do NOT add knowledge from outside the source.
- Do NOT infer or guess from general OSHA principles.
- Every claim must be traceable to the provided source text.
- Every word-for-word quote MUST be wrapped in {{...}}. Never quote without braces.
- Never put text in {{...}} unless it appears exactly in the source.
- Every section provided must be addressed in the body. If a section had no relevant content for the question, explicitly state that in the body.
- A verbatim quote in {{...}} must be a complete meaningful phrase — not a fragment. It must start at a natural boundary and stand alone in meaning.

"""


def _normalize(text: str) -> str:
    text = text.replace("\u00a7", "§").replace("\ufffd", "§")
    text = re.sub(r"\s+", " ", text).strip()
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
    spans = re.findall(r"\{\{(.+?)\}\}", body, re.DOTALL)

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
        retrieval_score = int((sum(top_scores) / len(top_scores)) * 100)
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

    hits = bedrock_kb.retrieve_for_section(query, sections, top_k=10)

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
    source_uri   = hits[0].get("source", "")

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

    clean_body = re.sub(r"\{\{(.+?)\}\}", r"**\1**", body, flags=re.DOTALL)

    return json.dumps({
        "type":               "generate_result",
        "title":              title,
        "body":               clean_body.strip(),
        "references":         _build_references(sections),
        "verbatim_quotes":    verified_quotes,
        "confidence_percent": confidence,
        "verbatim_percent":   verbatim_pct,
        "not_found":          "NOT FOUND IN SOURCE" in body,
        "source_uri":         source_uri,
        "disclaimer":         "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA.",
    })

