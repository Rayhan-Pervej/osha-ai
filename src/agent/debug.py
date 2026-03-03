import logging
from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

logger = logging.getLogger("osha.agent.debug")


def _truncate(text: str, max_chars: int = 30) -> str:
    text = str(text).strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


class AgentDebugCallback(BaseCallbackHandler):
    """Logs every LLM call, tool call, and tool result to the debug logger.

    Enable by setting log level to DEBUG:
      logging.getLogger("osha.agent.debug").setLevel(logging.DEBUG)
    """

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        model = serialized.get("kwargs", {}).get("model_id", serialized.get("name", "unknown"))
        logger.debug("\n" + "="*60)
        logger.debug(f"[LLM] Invoking: {model}")
        for i, p in enumerate(prompts):
            logger.debug(f"[LLM] Prompt[{i}]: {_truncate(p)}")

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list[list[BaseMessage]],
        **kwargs,
    ) -> None:
        model = serialized.get("kwargs", {}).get("model_id", serialized.get("name", "unknown"))
        logger.debug("\n" + "="*60)
        logger.debug(f"[LLM] Chat model invoking: {model}")
        for batch in messages:
            for msg in batch:
                role = msg.__class__.__name__.replace("Message", "")
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") if isinstance(c, dict) else str(c)
                        for c in content
                    )
                logger.debug(f"[LLM] [{role}]: {_truncate(str(content))}")

    def on_llm_end(self, response, **kwargs) -> None:
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", None) or str(getattr(gen, "message", gen))
                logger.debug(f"[LLM] Response: {_truncate(str(text))}")
                # Log tool calls if present
                msg = getattr(gen, "message", None)
                if msg and hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        logger.debug(
                            f"[LLM] → Tool call: {tc['name']}("
                            + ", ".join(f"{k}={v!r}" for k, v in tc.get("args", {}).items())
                            + ")"
                        )

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        logger.debug(f"[LLM] ERROR: {error}")


    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        name = serialized.get("name", "unknown_tool")
        logger.debug("-"*60)
        logger.debug(f"[TOOL] Executing: {name}")
        logger.debug(f"[TOOL] Input: {_truncate(input_str)}")

    def on_tool_end(self, output: str, **kwargs) -> None:
        logger.debug(f"[TOOL] Output: {_truncate(str(output))}")
        logger.debug("-"*60)

    def on_tool_error(self, error: Exception, **kwargs) -> None:
        logger.debug(f"[TOOL] ERROR: {error}")
        logger.debug("-"*60)


    def on_chain_start(self, serialized: dict, inputs: dict, **kwargs) -> None:
        name = serialized.get("name") or serialized.get("id", ["?"])[-1]
        logger.debug(f"[CHAIN] Start: {name}")

    def on_chain_end(self, outputs: dict, **kwargs) -> None:
        logger.debug(f"[CHAIN] End — keys: {list(outputs.keys())}")
