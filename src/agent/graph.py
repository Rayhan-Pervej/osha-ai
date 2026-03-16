import json
import logging

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import ToolMessage

from src.agent.state import AgentState
from src.agent.tools import all_tools
from src.agent.prompts.system import build_system_prompt
from src.agent.debug import AgentDebugCallback
from src.config import settings

logger = logging.getLogger(__name__)
debug_callback = AgentDebugCallback()

AGENT_SYSTEM_PROMPT = build_system_prompt()


def _build_llm():
    llm = ChatBedrockConverse(
        model=settings.BEDROCK_MODEL_ID,
        region_name=settings.AWS_REGION,
        temperature=settings.BEDROCK_TEMPERATURE,
        max_tokens=settings.BEDROCK_MAX_TOKENS,
        system=[{"text": AGENT_SYSTEM_PROMPT}],
    )
    return llm.bind_tools(all_tools)


_llm_with_tools = _build_llm()


def agent(state: AgentState):
    messages = list(state.get("messages") or [])
    logger.debug("[AGENT] Invoking LLM with %d messages", len(messages))
    try:
        response = _llm_with_tools.invoke(messages, config={"callbacks": [debug_callback]})
    except Exception as e:
        logger.error("[AGENT] LLM invocation failed: %s", e)
        from src.exceptions.errors import OshaAgentError
        raise OshaAgentError(f"LLM service unavailable: {e}") from e
    logger.debug("[AGENT] LLM response type: %s", type(response).__name__)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


def extract_output(state: AgentState) -> dict:
    messages = state["messages"]
    last_tool_msg = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)

    if last_tool_msg is None:
        return {"structured_output": None}

    if last_tool_msg.name == "search_regulations":
        try:
            payload = json.loads(last_tool_msg.content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[AGENT] Failed to parse search_regulations response: %r", last_tool_msg.content)
            payload = {"type": "search_no_results", "query": "", "message": last_tool_msg.content}
        return {"structured_output": payload}

    if last_tool_msg.name == "generate_answer":
        try:
            payload = json.loads(last_tool_msg.content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[AGENT] Failed to parse generate_answer response: %r", last_tool_msg.content)
            payload = {
                "type":               "generate_result",
                "title":              "",
                "body":               last_tool_msg.content,
                "references":         [],
                "verbatim_quotes":    [],
                "confidence_percent": 0,
                "verbatim_percent":   0,
                "not_found":          True,
                "source_uri":         "",
                "disclaimer":         "",
            }
        return {"structured_output": payload}

    return {"structured_output": None}


def _after_extract(state: AgentState) -> str:
    messages = state["messages"]
    last_tool_msg = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
    if last_tool_msg and last_tool_msg.name == "generate_answer":
        return END
    return "agent"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(all_tools))
    builder.add_node("extract_output", extract_output)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {
        "tools": "tools",
        END: END,
    })
    builder.add_edge("tools", "extract_output")
    builder.add_conditional_edges("extract_output", _after_extract, {
        "agent": "agent",
        END: END,
    })

    return builder


graph = build_graph().compile()
