from functools import wraps
from flask import request
from src.config import settings
from src.services.aws import get_dynamodb_client
from src.api.schemas.responses import error



def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return error("missing_key", "X-API-Key header is required", 401)

        client = get_dynamodb_client()
        response = client.get_item(
            TableName=settings.DYNAMODB_TABLE_API_KEYS,
            Key={"embed_key": {"S": api_key}},
        )
        item = response.get("Item")
        if not item or item.get("active", {}).get("BOOL") is False:
            return error("invalid_key", "Invalid or revoked API key", 401)

        allowed_domains = [d["S"] for d in item.get("allowed_domains", {}).get("L", [])]
        if allowed_domains:
            origin = request.headers.get("Origin", "")
            if not any(origin.endswith(d) for d in allowed_domains):
                return error("forbidden_origin", "Request origin not allowed", 403)

        request.client_id = item["client_id"]["S"]
        request.agent_id = item["agent_id"]["S"]

        return f(*args, **kwargs)
    return decorated


def require_admin_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_key = request.headers.get("X-Admin-Key")
        if not admin_key or admin_key != settings.ADMIN_API_KEY:
            return error("unauthorized", "Invalid or missing admin key", 401)
        return f(*args, **kwargs)
    return decorated
