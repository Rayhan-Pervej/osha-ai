import logging
from src.agent.state import AgentState
from src.rag.discover import discover
from src.exceptions.errors import OshaNoResultsError, OshaAgentError

logger = logging.getLogger(__name__)


def search_regulations(state: AgentState) -> dict:
    intent = state.get("intent", {})
    topic = intent.get("topic") or state.get("user_input", "")
    part_filter = intent.get("industry") # could be "1910", "1926", or null

    if not topic:
        raise OshaAgentError("search_regulations called without a topic in intent or user_input")
    

    try:
        result = discover(topic, part_filter)
        results = result.get("results", [])
    except OshaNoResultsError:
        results = []
    except Exception as e:
        raise OshaAgentError(f"Search failed unexpectedly: {e}") from e

    # Convert numpy.float64 scores to plain Python float so LangGraph
    # MemorySaver can serialize the state with msgpack
    sanitized = []
    for r in results:
        sanitized.append({**r, "score": float(r["score"]) if "score" in r else 0.0})

    logger.debug("Search returned %d results for topic: %s", len(sanitized), topic)
    return {"search_results": sanitized}
