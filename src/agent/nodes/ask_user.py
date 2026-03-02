from langgraph.types import interrupt, Command
from src.agent.state import AgentState
from src.exceptions.errors import OshaAgentError


def ask_user(state: AgentState) -> Command:
    question = state.get("clarification_question")

    if not question:
        raise OshaAgentError("ask_user called with no clarification_question in state")

    rounds = state.get("clarification_rounds", 0)

    # Graph pauses here — question returned to API caller
    # On resume, user_reply = value passed to Command(resume=...)
    user_reply = interrupt(question)

    updated_messages = state.get("messages", []) + [
        {"role": "assistant", "content": question},
        {"role": "user", "content": user_reply},
    ]

    return Command(
        update={
            "messages": updated_messages,
            "user_input": user_reply,
            "clarification_rounds": rounds + 1,
        },
        goto="understand_intent",
    )
