import uuid
import secrets
from datetime import datetime, timezone
from flask import Blueprint, request
from marshmallow import ValidationError
from src.api.middleware.auth import require_admin_key
from src.api.schemas.requests import CreateKeySchema, RotateKeySchema
from src.api.schemas.responses import success, error, validation_error
from src.config import settings
from src.services.aws import get_dynamodb_client

keys_bp = Blueprint("keys", __name__)
_create_schema = CreateKeySchema()
_rotate_schema = RotateKeySchema()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_key() -> str:
    return "osha_live_" + secrets.token_urlsafe(24)


@keys_bp.route("/keys", methods=["POST"])
@require_admin_key
def create_key():
    try:
        data = _create_schema.load(request.json or {})
    except ValidationError as exc:
        return validation_error(exc)

    client_id = data["client_id"]
    agent_id = data["agent_id"]
    allowed_domains = data["allowed_domains"] or []

    embed_key = _generate_key()
    client = get_dynamodb_client()
    client.put_item(
        TableName=settings.DYNAMODB_TABLE_API_KEYS,
        Item={
            "embed_key":       {"S": embed_key},
            "client_id":       {"S": client_id},
            "agent_id":        {"S": agent_id},
            "allowed_domains": {"L": [{"S": d} for d in allowed_domains]},
            "created_at":      {"S": _now()},
            "active":          {"BOOL": True},
        },
    )

    return success({
        "embed_key":  embed_key,
        "client_id":  client_id,
        "agent_id":   agent_id,
        "created_at": _now(),
    }, 201)


@keys_bp.route("/keys/rotate", methods=["POST"])
@require_admin_key
def rotate_key():
    try:
        data = _rotate_schema.load(request.json or {})
    except ValidationError as exc:
        return validation_error(exc)

    client_id = data["client_id"]
    agent_id = data["agent_id"]
    db = get_dynamodb_client()

    # find existing active key
    response = db.scan(
        TableName=settings.DYNAMODB_TABLE_API_KEYS,
        FilterExpression="client_id = :c AND agent_id = :a AND active = :t",
        ExpressionAttributeValues={
            ":c": {"S": client_id},
            ":a": {"S": agent_id},
            ":t": {"BOOL": True},
        },
    )
    items = response.get("Items", [])
    if not items:
        return error("key_not_found", "No active key found for this client/agent", 404)

    # revoke old key
    old_key = items[0]["embed_key"]["S"]
    db.update_item(
        TableName=settings.DYNAMODB_TABLE_API_KEYS,
        Key={"embed_key": {"S": old_key}},
        UpdateExpression="SET active = :f",
        ExpressionAttributeValues={":f": {"BOOL": False}},
    )

    # create new key
    new_key = _generate_key()
    db.put_item(
        TableName=settings.DYNAMODB_TABLE_API_KEYS,
        Item={
            "embed_key":       {"S": new_key},
            "client_id":       {"S": client_id},
            "agent_id":        {"S": agent_id},
            "allowed_domains": items[0].get("allowed_domains", {"L": []}).get("L", []) and items[0]["allowed_domains"],
            "created_at":      {"S": _now()},
            "active":          {"BOOL": True},
        },
    )

    return success({
        "embed_key":  new_key,
        "client_id":  client_id,
        "agent_id":   agent_id,
        "rotated_at": _now(),
    })


@keys_bp.route("/keys/<embed_key>", methods=["DELETE"])
@require_admin_key
def delete_key(embed_key):
    db = get_dynamodb_client()
    response = db.get_item(
        TableName=settings.DYNAMODB_TABLE_API_KEYS,
        Key={"embed_key": {"S": embed_key}},
    )
    if not response.get("Item"):
        return error("key_not_found", "Key not found", 404)

    db.update_item(
        TableName=settings.DYNAMODB_TABLE_API_KEYS,
        Key={"embed_key": {"S": embed_key}},
        UpdateExpression="SET active = :f",
        ExpressionAttributeValues={":f": {"BOOL": False}},
    )

    return success({"revoked": True, "embed_key": embed_key})
