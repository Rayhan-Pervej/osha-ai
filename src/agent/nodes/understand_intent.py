import logging
from src.agent.state import AgentState
from src.llm.chat import llm_json
from src.rag.prompts import INTENT_EXTRACTION_PROMPT
from src.exceptions.errors import OshaAgentError

logger = logging.getLogger(__name__)

def understand_intent(state: AgentState) -> dict:
    rounds = state.get("clarification_rounds", 0)

    converstion = '\n'.join(
        f"{m['role'].upper()}: {m['content']}"
        for m in state.get("messages", [])
    )

    user_msg = f"Conversation so far:\n{converstion}\n\nclarification_rounds:{rounds}"

    result = llm_json(INTENT_EXTRACTION_PROMPT, user_msg)

    if not result:
        raise OshaAgentError("Intent extraction return empty response from LLM")
    logger.debug("Intent extraction result: %s", result)


    return {
        "intent": result,
        "next_action": "search" if result.get("confident") else "clarify",
        "clarification_question": result.get("clarification_question"),
    }