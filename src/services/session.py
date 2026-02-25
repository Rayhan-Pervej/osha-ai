import json
import uuid
from datetime import datetime, timezone
from src.config import settings
from src.services.aws import get_dynamodb_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl() -> int:
    from time import time
    return int(time()) + settings.SESSION_TTL_SECONDS


def get_session(session_id: str) -> dict | None:
    client = get_dynamodb_client()
    resp = client.get_item(
        TableName=settings.DYNAMODB_TABLE_SESSIONS,
        Key={"session_id": {"S": session_id}},
    )
    item = resp.get("Item")
    if not item:
        return None
    return {
        "session_id": item["session_id"]["S"],
        "client_id": item["client_id"]["S"],
        "agent_id": item["agent_id"]["S"],
        "history": json.loads(item["history"]["S"]),
    }


def save_session(session_id: str, client_id: str, agent_id: str, history: list) -> str:
    capped = history[-( settings.SESSION_MAX_HISTORY * 2):]
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
    return session_id


def create_session(client_id: str, agent_id: str) -> str:
    session_id = str(uuid.uuid4())
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
    return session_id
