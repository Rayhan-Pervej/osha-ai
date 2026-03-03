import uuid
import logging
from flask import Blueprint, request
from langchain_core.messages import HumanMessage

from langgraph.errors import GraphRecursionError

from src.api.middleware.auth import require_api_key
from src.api.schemas.responses import success, error
from src.agent.graph import graph
from src.exceptions.errors import OshaAgentError

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
    thread_id = session_id or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10, 
    }

    try:
        # Every turn is just: add user message → invoke graph → get response
        result = graph.invoke(
            {"messages": [HumanMessage(content=query)]},
            config=config,
        )
    except GraphRecursionError:
        logger.warning("Agent hit recursion limit for session %s", thread_id)
        return error("agent_loop", "The agent could not complete the request. Please try rephrasing your question.", 500)
    except OshaAgentError as e:
        logger.error("Agent error: %s", e)
        return error("agent_error", str(e), 500)
    except Exception as e:
        logger.error("Unexpected error in /chat: %s", e)
        return error("internal_error", "An unexpected error occurred", 500)

    # The last message is the agent's response
    last_message = result["messages"][-1]
    response_text = last_message.content

    return success({
        "type": "message",
        "message": response_text,
        "session_id": thread_id,
    })
