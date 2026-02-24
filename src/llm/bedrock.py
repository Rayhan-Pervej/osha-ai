import json
import logging

from src.config import settings
from src.exceptions.errors import OshaGenerationError
from src.services.aws import get_bedrock_client

logger = logging.getLogger(__name__)


def invoke(system_prompt: str, user_message: str, history: list[dict] | None = None) -> str:
    messages = (history or []) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": "{"},
    ]
    client = get_bedrock_client()

    try:
        response = client.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": settings.BEDROCK_MAX_TOKENS,
                "temperature": settings.BEDROCK_TEMPERATURE,
                "system": system_prompt,
                "messages": messages,
            }),
        )
        body = json.loads(response["body"].read())
        raw_text = "{" + body['content'][0]['text'] 
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON despite prefill")
            return {"answer": raw_text, "sections_cited": [], "verbatim_quotes": [], "confidence_score": 0.0}
    except Exception as e:
        logger.error(f"Bedrock invoke failed: {e}")
        raise OshaGenerationError(str(e)) from e
