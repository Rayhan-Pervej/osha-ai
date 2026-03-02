import json
import logging

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage

from src.config import settings

logger = logging.getLogger(__name__)

__llm = ChatBedrockConverse(
    model=settings.BEDROCK_MODEL_ID,
    region_name=settings.AWS_REGION,
    temperature=settings.BEDROCK_TEMPERATURE,
    max_tokens=settings.BEDROCK_MAX_TOKENS)


def llm_json(system_prompt: str, usr_prompt: str) -> dict:
    """Call LLM with a system prompt and user message, return parsed JSON dict."""
    response = __llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=usr_prompt),
    ])

    text = response.content.strip()
    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON: %s", response.content)
        return {}