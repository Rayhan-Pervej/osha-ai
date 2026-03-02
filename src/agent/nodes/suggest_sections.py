import logging
from langgraph.types import interrupt, Command
from src.agent.state import AgentState
from src.llm.chat import llm_json
from src.rag.prompts import SECTION_SUGGESTER_PROMPT
from src.exceptions.errors import OshaAgentError

logger = logging.getLogger(__name__)


def suggest_sections(state: AgentState) -> Command:
    results = state.get("search_results", [])
    

    if not results:
        raise OshaAgentError("suggest_section called with empty search_results")
    
    top = results[:5]  # only top 5 to LLM

    results_text = "\n".join(
        f"{i+1}. section_id={r['section_id']} | title={r.get('title', '')} | "
        f"score={r.get('score', 0):.2f} | excerpt={r.get('excerpt', '')[:500]}"
        for i, r in enumerate(top)
    )

    situation = state.get('intent', {}).get('situation') or state.get('user_input', '')
    user_msg = f"User situation: {situation}\n\nSearch results:\n{results_text}"

    result = llm_json(SECTION_SUGGESTER_PROMPT, user_msg)

    if not result:
        raise OshaAgentError("Section suggester returned empty response from LLM")

    suggestion = result.get("suggestion_message", "Here are the relevant sections. Which one fits your situation?")
    logger.debug("Suggestion message generated, length: %d", len(suggestion))

    # Graph pauses here — suggestion shown to user
    user_reply = interrupt(suggestion)

    updated_messages = state.get("messages", []) + [
        {"role": "assistant", "content": suggestion},
        {"role": "user", "content": user_reply},
    ]

    return Command(
        update={
            "messages": updated_messages,
            "suggestion_message": suggestion,
            "user_input": user_reply,
        },
        goto="pick_or_chat",
    )