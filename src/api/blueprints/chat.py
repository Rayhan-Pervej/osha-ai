import uuid
import logging
from datetime import datetime, timezone
from flask import Blueprint, request
from langchain_core.messages import HumanMessage

from langgraph.errors import GraphRecursionError

from src.api.middleware.auth import require_api_key
from src.api.middleware.rate_limit import rate_limit
from src.api.schemas.responses import success, error
from src.agent.graph import graph
from src.exceptions.errors import OshaAgentError
from src.services.session import get_session, save_session, create_session, build_messages
from src.services.aws import get_dynamodb_client
from src.config import settings

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)


def _log_query(client_id, agent_id, thread_id, query, structured):
    """Write a query log entry to DynamoDB. Fails silently."""
    try:
        msg_type = structured.get("type", "message")
        returned_section_ids = ""
        generation_invoked = "N"

        if msg_type == "search_results":
            returned_section_ids = ",".join(
                r["section_id"] for r in structured.get("results", [])
            )
        elif msg_type == "message":
            generation_invoked = "Y"

        db = get_dynamodb_client()
        db.put_item(
            TableName=settings.DYNAMODB_TABLE_QUERY_LOGS,
            Item={
                "query_id":             {"S": str(uuid.uuid4())},
                "client_id":            {"S": client_id},
                "agent_id":             {"S": agent_id or ""},
                "session_id":           {"S": thread_id},
                "timestamp":            {"S": datetime.now(timezone.utc).isoformat()},
                "query_text":           {"S": query},
                "returned_section_ids": {"S": returned_section_ids},
                "locked_section_ids":   {"S": ""},
                "generation_invoked":   {"S": generation_invoked},
            },
        )
    except Exception as e:
        logger.warning("[CHAT] Failed to write query log: %s", e)


@chat_bp.route("/chat", methods=["POST"])
@require_api_key
@rate_limit
def chat_route():
    data = request.json or {}
    query = data.get("query", "").strip()
    session_id = data.get("session_id")

    if not query:
        return error("missing_query", "query is required", 400)

    client_id = request.client_id
    agent_id = request.agent_id
    thread_id = session_id or str(uuid.uuid4())

    logger.debug("[CHAT] thread_id=%s client_id=%s", thread_id, client_id)

    session = get_session(thread_id)
    if session is None:
        create_session(thread_id, client_id, agent_id)
        raw_history = []
    else:
        raw_history = session.get("history", [])

    prior_messages = build_messages(raw_history)

    config = {"recursion_limit": 10}

    try:
        result = graph.invoke(
            {"messages": prior_messages + [HumanMessage(content=query)]},
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

    structured = result.get("structured_output") or {
        "type": "message",
        "message": result["messages"][-1].content,
    }

    if structured.get("type") == "search_results":
        results = structured.get("results", [])
        section_list = "\n".join(
            f"  {i+1}. {r['section_id']} — {r.get('title', '')}"
            for i, r in enumerate(results)
        )
        assistant_history_content = (
            f"[Search results for: {structured.get('query', '')}]\n{section_list}\n"
            f"Please reply with the number or section ID you want to explore."
        )
    else:
        assistant_history_content = structured.get("message", "")

    updated_history = raw_history + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": assistant_history_content},
    ]
    save_session(thread_id, client_id=client_id, agent_id=agent_id, history=updated_history)

    _log_query(client_id, agent_id, thread_id, query, structured)

    structured["session_id"] = thread_id
    return success(structured)
