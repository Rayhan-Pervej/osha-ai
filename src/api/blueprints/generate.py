from flask import Blueprint, request
from marshmallow import ValidationError
from src.api.middleware.auth import require_api_key
from src.api.middleware.rate_limit import rate_limit
from src.api.schemas.requests import GenerateSchema
from src.api.schemas.responses import success, error, validation_error
from src.rag.generate import generate
from src.retrieval.bm25 import get_section_metadata
from src.services.logger import log_query
from src.services.session import get_session, save_session, create_session
from src.exceptions.errors import OshaDocumentNotFoundError, OshaGenerationError

generate_bp = Blueprint("generate", __name__)
_schema = GenerateSchema()


@generate_bp.route("/generate", methods=["POST"])
@require_api_key
@rate_limit
def generate_route():
    try:
        data = _schema.load(request.json or {})
    except ValidationError as exc:
        return validation_error(exc)

    query = data["query"]
    section_ids = data["section_ids"]
    client_id = request.client_id
    agent_id = request.agent_id
    session_id = data["session_id"]

    # load or create
    if session_id:
        session = get_session(session_id)
        if not session:
            return error("invalid_session", "Session not found or expired", 404)
        history = session["history"]
    else:
        session_id = create_session(client_id, agent_id)
        history = []

    # fetch locked sections directly by section_id (no BM25 re-scoring)
    locked_sections = []
    for sid in section_ids:
        try:
            locked_sections.append(get_section_metadata(sid))
        except OshaDocumentNotFoundError:
            pass

    if not locked_sections:
        return error("sections_not_found", "None of the provided section_ids were found", 404)

    # generate answer
    try:
        gen_result = generate(query, locked_sections, history=history)
    except OshaGenerationError as exc:
        return error("generation_failed", str(exc), 502)

    # save updated session
    updated_history = gen_result.get("history", history)
    save_session(session_id, client_id, agent_id, updated_history)

    log_query(
        client_id=client_id,
        agent_id=agent_id,
        query=query,
        returned_section_ids=section_ids,
        locked_section_ids=section_ids,
        generation_invoked=True,
    )
    
    return success({
        "query": query,
        "session_id": session_id,
        "locked_section_ids": section_ids,
        "generation_invoked": True,
        "answer": gen_result["answer"],
    })
