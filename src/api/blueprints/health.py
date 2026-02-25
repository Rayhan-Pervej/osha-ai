from datetime import datetime, timezone
from flask import Blueprint
from src.api.schemas.responses import success

health_bp = Blueprint("health", __name__)

@health_bp.route("/health", methods=["GET"])

def health():
    return success({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })