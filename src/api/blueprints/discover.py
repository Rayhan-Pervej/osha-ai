from flask import Blueprint, request
from marshmallow import ValidationError
from src.api.middleware.auth import require_api_key
from src.api.middleware.rate_limit import rate_limit
from src.api.schemas.requests import DiscoverSchema
from src.api.schemas.responses import success, error, validation_error
from src.rag.discover import discover
from src.services.logger import log_query
from src.exceptions.errors import OshaNoResultsError

discover_bp = Blueprint("discover", __name__)
_schema = DiscoverSchema()


@discover_bp.route("/discover", methods=["POST"])
@require_api_key
@rate_limit
def discover_route():
    try:
        data = _schema.load(request.json or {})
    except ValidationError as exc:
        return validation_error(exc)

    query = data["query"]
    part_filter = data["part_filter"]
    client_id = request.client_id
    agent_id = request.agent_id

    try:
        result = discover(query, part_filter=part_filter)
    except OshaNoResultsError:
        return error("no_results", f"No results found for query: '{query}'", 404)

    log_query(
        client_id=client_id,
        agent_id=agent_id,
        query=query,
        returned_section_ids=[r["section_id"] for r in result["results"]],
        locked_section_ids=[],
    )

    return success(result)
