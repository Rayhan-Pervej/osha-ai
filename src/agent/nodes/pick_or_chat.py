import logging
from langgraph.types import Command
from src.agent.state import AgentState
from src.llm.chat import llm_json
from src.rag.prompts import PICK_OR_CHAT_PROMPT
from src.exceptions.errors import OshaAgentError

logger = logging.getLogger(__name__)


def pick_or_chat(state: AgentState) -> Command:
    user_reply = state.get("user_input", "")
    suggestion = state.get("suggestion_message", "")

    if not user_reply:
        raise OshaAgentError("pick_or_chat called with no user_input in state")

    user_msg = f"Suggestion shown to user:\n{suggestion}\n\nUser replied: {user_reply}"
    result = llm_json(PICK_OR_CHAT_PROMPT, user_msg)
    route_val = result.get("route", "ambiguous")
    logger.debug("pick_or_chat routed to: %s", route_val)

    if route_val == "pick":
        return Command(goto="confirm_section")
    elif route_val == "new_query":
        return Command(
            update={"clarification_rounds": 0},
            goto="understand_intent",
        )
    else:  # ambiguous — re-show same list
        return Command(goto="suggest_sections")
