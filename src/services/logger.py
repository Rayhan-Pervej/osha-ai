import logging
import uuid
from datetime import datetime, timezone
from src.config import settings
from src.services.aws import get_dynamodb_client

logger = logging.getLogger(__name__)

def log_query(
        client_id: str,
        agent_id: str,
        query: str,
        returned_section_ids: list[str],
        locked_section_ids: list[str],
        generation_invoked: bool= False,
) -> str:
    query_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        "query_id":             {"S": query_id},
        "timestamp":            {"S": timestamp},
        "client_id":            {"S": client_id},
        "agent_id":             {"S": agent_id},
        "query_text":           {"S": query},
        "returned_section_ids": {"S": ",".join(returned_section_ids)},
        "locked_section_ids":   {"S": ",".join(locked_section_ids) if locked_section_ids else ""},
        "generation_invoked":   {"S": "Y" if generation_invoked else "N"},
    }

    try:
        client = get_dynamodb_client()
        client.put_item(TableName=settings.DYNAMODB_TABLE_QUERY_LOGS, Item=item)
        logging.info(f"Query logged: {query_id}")
    except Exception as e:
        logger.debug(f"DynamoDB log skipped: {e}")

    return query_id