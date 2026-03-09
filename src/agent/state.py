from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    structured_output: dict | None

    # For Manual flow Control
    # stage: str
    # original_query: str
    # refined_query: str
    # search_results: list
    # part_filter: str | None
    # ambiguity_parts: list
    # selected_section: str
    # rewritten_query: str
    # clarification_count: int
