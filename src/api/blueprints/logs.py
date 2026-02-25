from flask import Blueprint, request
from src.api.middleware.auth import require_admin_key
from src.api.schemas.responses import success, error
from src.config import settings
from src.services.aws import get_dynamodb_client

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/logs", methods=["GET"])
@require_admin_key
def get_logs():
    client_id = request.args.get("client_id")
    if not client_id:
        return error("missing_client_id", "client_id query parameter is required", 400)

    from_date = request.args.get("from")
    to_date = request.args.get("to")
    limit = int(request.args.get("limit", 100))

    db = get_dynamodb_client()

    filter_parts = ["client_id = :c"]
    expr_values = {":c": {"S": client_id}}

    if from_date:
        filter_parts.append("#ts >= :from")
        expr_values[":from"] = {"S": from_date}
    if to_date:
        filter_parts.append("#ts <= :to")
        expr_values[":to"] = {"S": to_date}

    kwargs = {
        "TableName": settings.DYNAMODB_TABLE_QUERY_LOGS,
        "FilterExpression": " AND ".join(filter_parts),
        "ExpressionAttributeValues": expr_values,
        "Limit": limit,
    }

    if from_date or to_date:
        kwargs["ExpressionAttributeNames"] = {"#ts": "timestamp"}

    resp = db.scan(**kwargs)
    items = resp.get("Items", [])

    logs = [
        {
            "log_id":               item.get("query_id", {}).get("S", ""),
            "client_id":            item.get("client_id", {}).get("S", ""),
            "agent_id":             item.get("agent_id", {}).get("S", ""),
            "timestamp":            item.get("timestamp", {}).get("S", ""),
            "query":                item.get("query_text", {}).get("S", ""),
            "returned_section_ids": item.get("returned_section_ids", {}).get("S", "").split(","),
            "locked_section_ids":   item.get("locked_section_ids", {}).get("S", "").split(","),
            "generation_invoked":   item.get("generation_invoked", {}).get("S", "N") == "Y",
        }
        for item in items
    ]

    return success({
        "client_id": client_id,
        "total": len(logs),
        "logs": logs,
    })
