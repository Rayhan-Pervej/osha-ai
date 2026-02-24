import json
import logging

from src.config import settings
from src.exceptions.errors import OshaGenerationError
from src.services.aws import get_bedrock_client

logger = logging.getLogger(__name__)


def invoke(system_prompt: str, user_message: str) -> str:
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
                "messages": [{"role": "user", "content": user_message}],
            }),
        )
        body = json.loads(response["body"].read())
        return body["content"][0]["text"]
    except Exception as e:
        logger.error(f"Bedrock invoke failed: {e}")
        raise OshaGenerationError(str(e)) from e
