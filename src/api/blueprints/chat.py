import uuid
import logging
from flask import Blueprint, request
from langgraph.types import Command

from src.api.middleware.auth import require_api_key
from src.api.schemas.responses import success, error
from src.agent.graph import graph
from src.exceptions.errors import OshaAgentError, OshaAgentSessionError

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat", methods=["POST"])
@require_api_key
def chat_route():
    data = request.json or {}
    query = data.get("query", "").strip()
    session_id = data.get("session_id")

    if not query:
        return error("missing_query", "query is required", 400)

    client_id = request.client_id
    agent_id = request.agent_id

    # thread_id is the LangGraph checkpointer key — ties all turns together
    if session_id:
        thread_id = session_id
    else:
        thread_id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Check if this thread already has an interrupted state (resuming)
        state_snapshot = graph.get_state(config)
        is_resuming = bool(state_snapshot.next)

        if is_resuming:
            # Resume graph from interrupt — pass user's reply
            result = graph.invoke(Command(resume=query), config=config)
        else:
            # Fresh start — build initial state
            initial_state = {
                "session_id": thread_id,
                "client_id": client_id,
                "agent_id": agent_id,
                "messages": [{"role": "user", "content": query}],
                "user_input": query,
                "clarification_rounds": 0,
            }
            result = graph.invoke(initial_state, config=config)

    except OshaAgentError as e:
        logger.error("Agent error: %s", e)
        return error("agent_error", str(e), 500)
    except Exception as e:
        logger.error("Unexpected error in /chat: %s", e)
        return error("internal_error", "An unexpected error occurred", 500)

    # Check if graph is interrupted again (waiting for user)
    state_after = graph.get_state(config)
    if state_after.next:
        # Graph paused — get the interrupt value (question or suggestion)
        interrupts = result.get("__interrupt__", [])
        message = interrupts[0].value if interrupts else "Please provide more information."
        return success({
            "type": "clarification",
            "message": message,
            "session_id": thread_id,
        })

    # Graph completed — return final answer
    final_answer = result.get("final_answer", {})
    return success({
        "type": "answer",
        "answer": final_answer,
        "section_used": result.get("locked_section_id"),
        "session_id": thread_id,
    })
