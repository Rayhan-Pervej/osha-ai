from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.agent.state import AgentState
from src.agent.nodes.understand_intent import understand_intent
from src.agent.nodes.ask_user import ask_user
from src.agent.nodes.search_regulations import search_regulations
from src.agent.nodes.suggest_sections import suggest_sections
from src.agent.nodes.pick_or_chat import pick_or_chat
from src.agent.nodes.confirm_section import confirm_section
from src.agent.nodes.generate_answer import generate_answer


def _route(state: AgentState) -> str:
    return state.get("next_action", "clarify")


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("understand_intent",  understand_intent)
    builder.add_node("ask_user",           ask_user)
    builder.add_node("search_regulations", search_regulations)
    builder.add_node("suggest_sections",   suggest_sections)
    builder.add_node("pick_or_chat",       pick_or_chat)
    builder.add_node("confirm_section",    confirm_section)
    builder.add_node("generate_answer",    generate_answer)

    builder.add_edge(START, "understand_intent")
    builder.add_conditional_edges("understand_intent", _route, {
        "clarify": "ask_user",
        "search":  "search_regulations",
    })
    builder.add_edge("search_regulations", "suggest_sections")
    builder.add_edge("confirm_section",    "generate_answer")
    builder.add_edge("generate_answer",    END)

    return builder


checkpointer = MemorySaver()
graph = build_graph().compile(checkpointer=checkpointer)
