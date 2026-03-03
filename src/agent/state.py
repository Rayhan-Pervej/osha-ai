from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Minimal state for the tool-calling OSHA agent.

    `messages` is the only field that accumulates — it holds the full
    LangChain message history (HumanMessage, AIMessage, ToolMessage).
    """
    messages: Annotated[list, add_messages]
