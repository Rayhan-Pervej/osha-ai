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

    logger.debug("[BEDROCK] Model: %s | max_tokens: %s | temperature: %s",
                 settings.BEDROCK_MODEL_ID, settings.BEDROCK_MAX_TOKENS, settings.BEDROCK_TEMPERATURE)
    logger.debug("[BEDROCK] System prompt length: %d chars", len(system_prompt))
    logger.debug("[BEDROCK] User message length: %d chars", len(user_message))
    logger.debug("[BEDROCK] History messages: %d", len(history or []))

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
        logger.debug("[BEDROCK] Response stop_reason: %s | input_tokens: %s | output_tokens: %s",
                     body.get("stop_reason"),
                     body.get("usage", {}).get("input_tokens"),
                     body.get("usage", {}).get("output_tokens"))
        raw_text = "{" + body['content'][0]['text']
        logger.debug("[BEDROCK] Raw response (first 300 chars): %s", raw_text[:300])
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON despite prefill")
            return {"answer": raw_text, "sections_cited": [], "verbatim_quotes": [], "confidence_score": 0.0}
    except Exception as e:
        logger.error(f"Bedrock invoke failed: {e}")
        raise OshaGenerationError(str(e)) from e


def invoke_raw(prompt: str) -> str:
    client = get_bedrock_client()
    logger.debug("[BEDROCK] invoke_raw prompt length: %d chars", len(prompt))
    try:
        response = client.converse(
            modelId=settings.BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.0},
        )
        result = response["output"]["message"]["content"][0]["text"]
        logger.debug("[BEDROCK] invoke_raw response length: %d chars", len(result))
        return result
    except Exception as e:
        logger.error("[BEDROCK] invoke_raw failed: %s", e)
        raise OshaGenerationError(str(e)) from e