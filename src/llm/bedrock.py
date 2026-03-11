import logging

from pydantic import BaseModel
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage

from src.config import settings
from src.exceptions.errors import OshaGenerationError

logger = logging.getLogger(__name__)


class GenerationOutput(BaseModel):
    title: str
    body: str


def _build_llm() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model=settings.BEDROCK_MODEL_ID,
        region_name=settings.AWS_REGION,
        temperature=settings.BEDROCK_TEMPERATURE,
        max_tokens=settings.BEDROCK_MAX_TOKENS,
    )


_llm = _build_llm()
_structured_llm = _llm.with_structured_output(GenerationOutput)


def invoke(system_prompt: str, user_message: str) -> dict:
    from langchain_core.messages import SystemMessage
    try:
        result: GenerationOutput = _structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])
        return result.model_dump()
    except Exception as e:
        logger.error("[BEDROCK] invoke failed: %s", e)
        raise OshaGenerationError(str(e)) from e


def invoke_raw(prompt: str) -> str:
    from langchain_core.messages import HumanMessage as HM
    llm = ChatBedrockConverse(
        model=settings.BEDROCK_MODEL_ID,
        region_name=settings.AWS_REGION,
        temperature=0.0,
        max_tokens=512,
    )
    try:
        response = llm.invoke([HM(content=prompt)])
        return response.content
    except Exception as e:
        logger.error("[BEDROCK] invoke_raw failed: %s", e)
        raise OshaGenerationError(str(e)) from e
