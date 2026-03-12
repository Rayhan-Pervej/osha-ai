import json
import logging
from datetime import datetime, timezone
from src.config import settings
from src.services.aws import get_dynamodb_client
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

logger = logging.getLogger(__name__)

_SUMMARY_THRESHOLD = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl() -> int:
    from time import time
    return int(time()) + settings.SESSION_TTL_SECONDS


def get_session(session_id: str) -> dict | None:
    client = get_dynamodb_client()
    response = client.get_item(
        TableName=settings.DYNAMODB_TABLE_SESSIONS,
        Key={"session_id": {"S": session_id}},
    )
    item = response.get("Item")
    if not item:
        return None
    try:
        return {
            "session_id": item["session_id"]["S"],
            "client_id": item["client_id"]["S"],
            "agent_id": item["agent_id"]["S"],
            "history": json.loads(item["history"]["S"]) if item.get("history") else [],
        }
    except (json.JSONDecodeError, KeyError):
        return None



def save_session(session_id: str, client_id: str, agent_id: str, history: list) -> str:
    capped = history[-(settings.SESSION_MAX_HISTORY * 2):]
    try:
        client = get_dynamodb_client()
        client.put_item(
            TableName=settings.DYNAMODB_TABLE_SESSIONS,
            Item={
                "session_id": {"S": session_id},
                "client_id":  {"S": client_id},
                "agent_id":   {"S": agent_id},
                "history":    {"S": json.dumps(capped)},
                "updated_at": {"S": _now()},
                "ttl":        {"N": str(_ttl())},
            },
        )
    except Exception as e:
        logger.error("[SESSION] Failed to save session %s: %s", session_id, e)
    return session_id


def create_session(session_id: str, client_id: str, agent_id: str) -> str:
    try:
        client = get_dynamodb_client()
        client.put_item(
            TableName=settings.DYNAMODB_TABLE_SESSIONS,
            Item={
                "session_id": {"S": session_id},
                "client_id":  {"S": client_id},
                "agent_id":   {"S": agent_id},
                "history":    {"S": "[]"},
                "created_at": {"S": _now()},
                "updated_at": {"S": _now()},
                "ttl":        {"N": str(_ttl())},
            },
        )
    except Exception as e:
        logger.error("[SESSION] Failed to create session %s: %s", session_id, e)
    return session_id



def build_messages(history: list) -> list:
    """Convert stored history into LangChain messages.
    
    If history is long, older turns are replaced with a single summary message.
    Recent turns (last 4) are always kept verbatim.
    """

    if not history:
        return []
    
    if len(history) <= _SUMMARY_THRESHOLD:
        message = []

        for msg in history:
            if msg["role"] == "user":
                message.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                message.append(AIMessage(content=msg["content"]))
        return message
    
    old_turns = history[:-4]
    recent_turns = history[-4:]

    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in old_turns])


    summary_prompt = (
        "Summarize the following OSHA compliance conversation in 3-5 sentences. "
        "Focus on: what regulations were discussed, what sections were cited, "
        "and what the user was trying to find out.\n\n"
        f"{history_text}"
    )


    from src.llm import bedrock

    logger.debug("[SESSION] Summarizing %d old turns into summary message", len(old_turns))
    try:
        summary_text = bedrock.invoke_raw(summary_prompt)
        if not summary_text:
            raise ValueError("Empty summary returned")
        logger.debug("[SESSION] Summary generated: %d chars", len(summary_text))
    except Exception as e:
        logger.warning("[SESSION] Summarization failed: %s — using fallback", e)
        summary_text = f"[Earlier conversation covered {len(old_turns)//2} topics]"

    messages = [SystemMessage(content=f"Conversation summary: {summary_text}")]
    for msg in recent_turns:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    return messages



