import logging
from src.agent.state import AgentState
from src.rag.generate import generate
from src.exceptions.errors import OshaAgentError, OshaGenerationError

logger = logging.getLogger(__name__)


def generate_answer(state: AgentState) -> dict:
    locked = state.get("locked_section")
    query = state.get("user_input", "")

    if not locked:
        raise OshaAgentError("generate_answer called with no locked_section in state")
    if not query:
        raise OshaAgentError("generate_answer called with no user_input in state")

    history = [
        m for m in state.get("messages", [])
        if m.get("role") in ("user", "assistant")
    ]

    try:
        result = generate(query, [locked], history=history)
    except OshaGenerationError as e:
        raise OshaAgentError(f"Answer generation failed: {e}") from e

    updated_messages = state.get("messages", []) + [
        {"role": "assistant", "content": result["answer"].get("answer", "")},
    ]

    logger.debug("Answer generated for section: %s", state.get("locked_section_id"))
    return {
        "final_answer": result["answer"],
        "messages": updated_messages,
    }
