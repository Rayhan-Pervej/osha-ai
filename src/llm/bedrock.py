import json
import logging

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from src.config import settings
from src.exceptions.errors import OshaGenerationError

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"summary", "bullets", "why", "disclaimer"}

_REPAIR_PROMPT = (
    "You are a JSON repair assistant. The following JSON is broken or incomplete. "
    "Fix it so it is valid and return ONLY the corrected JSON object. No markdown, no explanation.\n\n"
    "Broken JSON:\n{broken}"
)

_RETRY_PROMPT = (
    "Your previous response was missing required fields: {missing}.\n"
    "Required fields: summary, bullets, why, disclaimer.\n\n"
    "Previous (incomplete) response:\n{previous}\n\n"
    "Original question:\n{question}\n\n"
    "Return a complete JSON object with ALL required fields."
)


def _build_llm() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model=settings.BEDROCK_MODEL_ID,
        region_name=settings.AWS_REGION,
        temperature=settings.BEDROCK_TEMPERATURE,
        max_tokens=settings.BEDROCK_MAX_TOKENS,
    )


_json_parser = JsonOutputParser()


def invoke(system_prompt: str, user_message: str, history: list[dict] | None = None) -> dict:
    logger.debug("[BEDROCK] Model: %s | max_tokens: %s | temperature: %s",
                 settings.BEDROCK_MODEL_ID, settings.BEDROCK_MAX_TOKENS, settings.BEDROCK_TEMPERATURE)
    logger.debug("[BEDROCK] System prompt length: %d chars", len(system_prompt))
    logger.debug("[BEDROCK] User message length: %d chars", len(user_message))
    logger.debug("[BEDROCK] History messages: %d", len(history or []))

    llm = _build_llm()

    lc_messages = [SystemMessage(content=system_prompt)]
    for msg in (history or []):
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        else:
            lc_messages.append(AIMessage(content=msg["content"]))
    lc_messages.append(HumanMessage(content=user_message))

    try:
        response = llm.invoke(lc_messages)
        raw_text = response.content
        logger.debug("[BEDROCK] Raw response (first 300 chars): %s", raw_text[:300])

        # OutputFixingParser equivalent: parse JSON, repair via LLM if broken
        try:
            parsed = _json_parser.parse(raw_text)
        except Exception:
            logger.warning("[BEDROCK] Invalid JSON, attempting LLM repair")
            try:
                fix_response = llm.invoke([
                    HumanMessage(content=_REPAIR_PROMPT.format(broken=raw_text))
                ])
                parsed = _json_parser.parse(fix_response.content)
                logger.info("[BEDROCK] JSON repair succeeded")
            except Exception as fix_err:
                logger.error("[BEDROCK] JSON repair failed: %s", fix_err)
                return {"summary": raw_text, "bullets": [], "why": "", "disclaimer": ""}

        # RetryWithErrorOutputParser equivalent: retry if required fields missing
        missing = _REQUIRED_FIELDS - set(parsed.keys())
        if missing:
            logger.warning("[BEDROCK] Missing fields %s, retrying with error context", missing)
            try:
                retry_response = llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                    AIMessage(content=json.dumps(parsed)),
                    HumanMessage(content=_RETRY_PROMPT.format(
                        missing=sorted(missing),
                        previous=json.dumps(parsed),
                        question=user_message,
                    )),
                ])
                parsed = _json_parser.parse(retry_response.content)
                logger.info("[BEDROCK] Retry succeeded, fields: %s", set(parsed.keys()))
            except Exception as retry_err:
                logger.error("[BEDROCK] Retry failed: %s", retry_err)

        return parsed

    except Exception as e:
        logger.error("Bedrock invoke failed: %s", e)
        raise OshaGenerationError(str(e)) from e


def invoke_raw(prompt: str) -> str:
    logger.debug("[BEDROCK] invoke_raw prompt length: %d chars", len(prompt))
    llm = ChatBedrockConverse(
        model=settings.BEDROCK_MODEL_ID,
        region_name=settings.AWS_REGION,
        temperature=0.0,
        max_tokens=512,
    )
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        result = response.content
        logger.debug("[BEDROCK] invoke_raw response length: %d chars", len(result))
        return result
    except Exception as e:
        logger.error("[BEDROCK] invoke_raw failed: %s", e)
        raise OshaGenerationError(str(e)) from e
