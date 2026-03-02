from typing import TypedDict


class AgentState(TypedDict):
    session_id: str
    client_id: str
    agent_id: str
    messages: list[dict]            # full conversation history [{role, content}]
    user_input: str                 # current user message
    intent: dict                    # {industry, situation, topic, confident}
    next_action: str                # "clarify" | "search"
    clarification_question: str     # question to send back if clarifying
    clarification_rounds: int       # max 2 before forcing a search
    search_results: list[dict]      # results from discover()
    suggestion_message: str         # human-friendly numbered list shown to user
    locked_section_id: str          # section chosen by user
    locked_section: dict            # full section dict for generate()
    final_answer: dict              # output from generate()
