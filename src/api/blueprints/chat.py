import uuid
import logging
from datetime import datetime, timezone
from flask import Blueprint, request
from langchain_core.messages import HumanMessage
from marshmallow import ValidationError
from src.api.schemas.requests import ChatRequestSchema
from src.api.schemas.responses import success, error, validation_error

from langgraph.errors import GraphRecursionError

from src.api.middleware.auth import require_api_key
from src.api.middleware.rate_limit import rate_limit
from src.agent.graph import graph
from src.exceptions.errors import OshaAgentError
from src.services.session import get_session, save_session, create_session, build_messages
from src.services.aws import get_dynamodb_client
from src.config import settings

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)
_chat_schema = ChatRequestSchema()


def _log_query(client_id, agent_id, thread_id, query, structured):
    """Write a query log entry to DynamoDB. Fails silently."""
    try:
        msg_type = structured.get("type", "message")
        returned_section_ids = ""
        generation_invoked = "N"

        if msg_type == "search_results":
            returned_section_ids = ",".join(
                r["section"] for r in structured.get("results", [])
            )
        elif msg_type == "generate_result":
            generation_invoked = "Y"
            returned_section_ids = ",".join(
                r.get("section", "") for r in structured.get("references", [])
            )

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
    try:
        data = _chat_schema.load(request.json or {})
    except ValidationError as exc:
        return validation_error(exc)
    
    query = data["query"].strip()
    session_id = data.get("session_id")

    client_id = request.client_id
    agent_id = getattr(request, "agent_id", "")
    thread_id = session_id or str(uuid.uuid4())

    logger.debug("[CHAT] thread_id=%s client_id=%s", thread_id, client_id)

    session = get_session(thread_id)
    if session is None:
        create_session(thread_id, client_id, agent_id)
        raw_history = []
    else:
        if session.get("client_id") != client_id:
            return error("forbidden", "You do not have access to this session", 403)
        raw_history = session.get("history", [])

    prior_messages = build_messages(raw_history)

    initial_state = {
        "messages": prior_messages + [HumanMessage(content=query)],
        "structured_output": None,
    }

    config = {"recursion_limit": settings.AGENT_RECURSION_LIMIT}

    try:
        result = graph.invoke(initial_state, config=config)
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
        "message": result["messages"][-1].content if result.get("messages") and len(result["messages"]) > 0 else "No response generated.",
    }

    msg_type = structured.get("type")
    if msg_type == "search_results":
        results = structured.get("results", [])
        section_list = "\n".join(
            f"  {i+1}. {r['section']} — {r.get('title', '')}"
            for i, r in enumerate(results)
        )
        assistant_history_content = (
            f"[Search results for: {structured.get('query', '')}]\n{section_list}\n"
            f"Please reply with the number or section ID you want to explore."
        )
    elif msg_type == "generate_result":
        refs = ", ".join(r.get("section", "") for r in structured.get("references", []))
        assistant_history_content = f"[Generated answer: {structured.get('title', '')}] ({refs})\n{structured.get('body', '')}"
    else:
        assistant_history_content = result["messages"][-1].content if result.get("messages") and len(result["messages"]) > 0 else "No response generated."

    updated_history = raw_history + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": assistant_history_content},
    ]
    save_session(thread_id, client_id=client_id, agent_id=agent_id, history=updated_history)

    _log_query(client_id, agent_id, thread_id, query, structured)

    return success({**structured, "session_id": thread_id})
