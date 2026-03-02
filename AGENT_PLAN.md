# OSHA AI — Agentic Mode Implementation

## Context

The client's requirement:

> People don't know the specific OSHA section — they only know their situation.
> Example: HR manager needs forklift training info. They know it's a warehouse. The agent
> should figure out that warehouse = General Industry (Part 1910) and find the right section.

**Goal:** Replace the manual discover → lock → generate flow with a LangGraph agent that
clarifies the user's situation, finds the right regulation, and answers — without the user
ever needing to know a section number.

---

## Tech Stack

- **LangGraph** — graph execution engine (nodes + edges + state + interrupt/resume)
- **langchain-aws** — `ChatBedrockConverse` wrapper for LangGraph nodes
- **MemorySaver** — in-process LangGraph checkpointer; keyed by `thread_id` (= session_id)
- **Existing `discover()`** — called inside `search_regulations` node
- **Existing `generate()`** — called inside `generate_answer` node
- **Existing Flask API** — new `/chat` blueprint added alongside existing endpoints

---

## Packages Added to requirements.txt

```
langgraph>=1.0.10
langchain-aws>=1.3.1
langchain-core>=1.2.16
```

---

## Folder Structure (Implemented)

```
osha-ai/
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py             ← AgentState TypedDict
│   │   ├── graph.py             ← LangGraph graph definition + compile
│   │   └── nodes/
│   │       ├── __init__.py
│   │       ├── understand_intent.py
│   │       ├── ask_user.py
│   │       ├── search_regulations.py
│   │       ├── suggest_sections.py
│   │       ├── pick_or_chat.py
│   │       ├── confirm_section.py
│   │       └── generate_answer.py
│   ├── llm/
│   │   ├── __init__.py
│   │   └── chat.py              ← ChatBedrockConverse wrapper (llm_json)
│   ├── rag/
│   │   ├── prompts.py           ← EXISTING + 4 new agent prompts appended
│   │   ├── discover.py          ← EXISTING — unchanged
│   │   └── generate.py          ← EXISTING — unchanged
│   ├── exceptions/
│   │   └── errors.py            ← Added OshaAgentError, OshaAgentSessionError
│   ├── api/
│   │   ├── blueprints/
│   │   │   └── chat.py          ← NEW — POST /chat endpoint
│   │   └── app.py               ← Registered chat_bp
├── demo/
│   └── app.py                   ← Full rewrite — single chat interface using /chat
```

---

## Graph Flow

```
[START]
   ↓
[understand_intent]  ── intent JSON extracted via LLM
   ↓
[route]  ─── "clarify" ──→ [ask_user] ──→ INTERRUPT ──→ user replies ──→ [understand_intent]
   |
   └── "search" ──→ [search_regulations] ──→ [suggest_sections] ──→ INTERRUPT
                                                                         ↓
                                                                  [pick_or_chat]
                                                                  /      |       \
                                                              "pick"  "ambiguous"  "new_query"
                                                                ↓        ↓              ↓
                                                      [confirm_section]  [suggest_sections]  [understand_intent]
                                                                ↓
                                                        [generate_answer]
                                                                ↓
                                                             [END]
```

**User after `suggest_sections` has 3 paths:**
1. **Clear pick** ("first one", "1910.178") → `confirm_section` → `generate_answer`
2. **Ambiguous** ("not sure", "maybe?") → back to `suggest_sections` (re-show same list)
3. **New query** ("actually I need PPE info") → back to `understand_intent` (fresh search)

---

## Node Descriptions

| Node | Purpose |
|---|---|
| `understand_intent` | Calls LLM with `INTENT_EXTRACTION_PROMPT`, extracts `{industry, topic, confident, clarification_question}` |
| `ask_user` | Calls `interrupt(question)`, resumes by updating `user_input` and looping back |
| `search_regulations` | Calls `discover(topic, part_filter)`, sanitizes numpy float64 scores to Python float |
| `suggest_sections` | Calls LLM with `SECTION_SUGGESTER_PROMPT`, calls `interrupt(suggestion_message)` |
| `pick_or_chat` | Calls LLM with `PICK_OR_CHAT_PROMPT`, routes via `Command(goto=...)` |
| `confirm_section` | Calls LLM with `CONFIRM_SECTION_PROMPT`, resolves user pick to `section_id` |
| `generate_answer` | Calls existing `generate()`, stores result in `final_answer` |

---

## Key Files

### `src/agent/state.py` — AgentState TypedDict

```python
class AgentState(TypedDict):
    session_id: str
    client_id: str
    agent_id: str
    messages: list[dict]
    user_input: str
    intent: dict               # {industry, topic, confident, clarification_question}
    search_results: list[dict]
    locked_section_id: str
    locked_section: dict
    final_answer: dict
    next_action: str           # "clarify" | "search"
    suggestion_message: str
    clarification_rounds: int
```

### `src/llm/chat.py` — LLM wrapper

```python
__llm = ChatBedrockConverse(model=settings.BEDROCK_MODEL_ID, ...)

def llm_json(system_prompt, usr_prompt) -> dict:
    # Calls __llm.invoke([SystemMessage, HumanMessage])
    # Strips ```json code fences from response
    # Returns parsed dict (or {} on failure)
```

### `src/rag/prompts.py` — Agent prompts (appended)

- `INTENT_EXTRACTION_PROMPT` — extracts industry/topic/confident from user message
- `SECTION_SUGGESTER_PROMPT` — formats search results as numbered list for user
- `PICK_OR_CHAT_PROMPT` — routes user reply to "pick", "ambiguous", or "new_query"
- `CONFIRM_SECTION_PROMPT` — maps natural language pick to exact section_id

### `src/api/blueprints/chat.py` — POST /chat

- Checks `graph.get_state(config).next` to detect interrupted (resume) vs fresh start
- Fresh: `graph.invoke(initial_state, config)`
- Resume: `graph.invoke(Command(resume=query), config)`
- Returns `{"type": "clarification", "message": ..., "session_id": ...}` or `{"type": "answer", ...}`

---

## Session Persistence

LangGraph `MemorySaver` checkpoints state between HTTP requests using `thread_id`.
The `session_id` from the client maps 1:1 to `thread_id` in LangGraph config:

```python
config = {"configurable": {"thread_id": session_id}}
```

No DynamoDB needed for graph state — MemorySaver holds it in process memory.
(Note: state is lost on server restart — acceptable for demo/phase 1.)

---

## Key Implementation Notes

- **numpy.float64 serialization**: BM25 scores are numpy floats. Cast to `float()` in
  `search_regulations.py` before storing in state — MemorySaver uses msgpack and can't
  serialize numpy types.
- **Markdown code fences**: LLM sometimes wraps JSON in ` ```json ``` ` blocks.
  `llm_json()` strips these before `json.loads()`.
- **ChatBedrockConverse**: Use `.invoke([...])`, NOT `__llm(...)` (not callable).
- **interrupt()**: Raises `GraphInterrupt` internally — do not catch it. LangGraph handles it.
- **Max clarification rounds**: `clarification_rounds` tracked in state, capped at 2.

---

## API Contract

### Request
```json
POST /chat
{
  "query": "I have 5 new forklift drivers that need to be trained",
  "session_id": "optional — omit for new session"
}
```

### Response: Clarification needed
```json
{
  "data": {
    "type": "clarification",
    "message": "Are these forklifts used in a warehouse or on a construction site?",
    "session_id": "abc123"
  }
}
```

### Response: Answer ready
```json
{
  "data": {
    "type": "answer",
    "answer": {
      "answer": "...",
      "sections_cited": ["1910.178"],
      "verbatim_quotes": ["..."],
      "display_pct": 87,
      "display_label": "Exact Match"
    },
    "section_used": "1910.178",
    "session_id": "abc123"
  }
}
```

---

## Tested Example Flow

```
User:  "I need to know about fall protection requirements for my workers"
Agent: "Are these workers in construction or general industry (warehouse/manufacturing)?"
User:  "warehouse, general industry"
Agent: [searches Part 1910, suggests 1910.28, 1910.29, 1910.21]
       "Here are the most relevant sections: ..."
User:  "1910.28"
Agent: [generates answer with verbatim federal OSHA citations]
       → 29 CFR 1910.28 — Walking-Working Surfaces
       → 4-foot threshold for general industry
       → display_pct: 33%, Partial Match
```

Result was correct federal OSHA answer (vs competitor who cited California OSHA with wrong 7.5ft threshold).
