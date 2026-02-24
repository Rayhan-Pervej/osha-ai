import json
import logging
import boto3
from src.config import settings
from src.rag.utils.extract_relevant_texts import extract_relevant_window

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an OSHA compliance assistant for nonprofit organizations.
You answer ONLY using the regulatory text provided. No outside knowledge. No inference.

RULES:
- Quote regulatory text verbatim. Do not paraphrase.
- If the answer is not in the provided text, say exactly: "NOT FOUND IN SOURCE"
- Never speculate or infer beyond what is explicitly written.
- Separate verbatim regulatory text from any structural formatting.

REQUIRED RESPONSE FORMAT:
**Regulatory Text (Verbatim):**
[Exact text from the source. No paraphrasing.]

**Source:**
- Document: [document name]
- Section: [section ID]
- Path: [hierarchical path]

**Confidence Score:**
[X%] — [Exact match / Partial match / Keyword match only]

**Verbatim Score:**
[X%] — Percentage of the answer drawn directly from verbatim source text

**Disclaimer:**
This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA (1-800-321-6742)."""


def get_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def generate(query: str, locked_sections: list[dict]) -> dict:
    """Send locked regulatory text + user question to Claude and return the answer."""
    if not locked_sections:
        raise ValueError("No locked sections provided. Run search first and lock section IDs.")

    context = _build_context(locked_sections, query)
    user_message = f"LOCKED REGULATORY TEXT:\n{context}\n\nUSER QUESTION:\n{query}"

    client = get_client()
    response = client.invoke_model(
        modelId=settings.BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": settings.BEDROCK_MAX_TOKENS,
            "temperature": settings.BEDROCK_TEMPERATURE,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
        }),
    )

    body = json.loads(response["body"].read())
    return {
        "query": query,
        "locked_section_ids": [s.get("section_id") for s in locked_sections],
        "answer": body["content"][0]["text"],
        "generation_invoked": True,
    }


def _build_context(locked_sections: list[dict], query: str) -> str:
    """Assemble context from locked sections, extracting only the relevant window from each."""
    parts = []
    for s in locked_sections:
        local_path = s.get("local_path", "")
        raw_content = s.get("raw_content", "")
        if local_path:
            try:
                with open(local_path, encoding="utf-8") as f:
                    text = f.read()
                excerpt = extract_relevant_window(text, query, max_chars=10000)
            except Exception as e:
                logger.warning(f"Could not read file {local_path}: {e}")
                excerpt = raw_content or s.get("excerpt", "")
        elif raw_content:
            excerpt = extract_relevant_window(raw_content, query, max_chars=10000)
        else:
            excerpt = s.get("excerpt", "")

        parts.append(
            f"[Section: {s.get('section_id', 'unknown')}]\n"
            f"Source: {s.get('source', '')}\n"
            f"Title: {s.get('title', '')}\n"
            f"Path: {s.get('path', '')}\n"
            f"Text:\n{excerpt}"
        )
    return "\n\n---\n\n".join(parts)
