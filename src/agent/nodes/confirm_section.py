import logging
from src.agent.state import AgentState
from src.llm.chat import llm_json
from src.rag.prompts import CONFIRM_SECTION_PROMPT
from src.retrieval.bm25 import get_section_metadata
from src.exceptions.errors import OshaAgentError, OshaDocumentNotFoundError

logger = logging.getLogger(__name__)


def confirm_section(state: AgentState) -> dict:
    results = state.get("search_results", [])
    user_reply = state.get("user_input", "")
    suggestion = state.get("suggestion_message", "")

    if not results:
        raise OshaAgentError("confirm_section called with empty search_results")

    results_text = "\n".join(
        f"{i+1}. section_id={r['section_id']} | title={r.get('title', '')}"
        for i, r in enumerate(results[:4])
    )
    user_msg = f"Suggestion shown:\n{suggestion}\n\nAvailable sections:\n{results_text}\n\nUser said: {user_reply}"

    result = llm_json(CONFIRM_SECTION_PROMPT, user_msg)
    section_id = result.get("section_id")

    if not section_id:
        raise OshaAgentError("confirm_section LLM could not map user reply to a section_id")

    # Find full section dict from search results first
    locked = next((r for r in results if r.get("section_id") == section_id), None)

    # Fallback: fetch metadata directly from index
    if not locked:
        try:
            locked = get_section_metadata(section_id)
        except OshaDocumentNotFoundError:
            raise OshaAgentError(f"Section '{section_id}' not found in index")

    logger.debug("Section confirmed: %s", section_id)
    return {
        "locked_section_id": section_id,
        "locked_section": locked,
    }
