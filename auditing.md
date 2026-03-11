# OSHA-AI System Audit

Root-to-leaf function-level documentation. Follows the exact execution path of a single POST /chat request.

---

## LAYER 1 — HTTP Entry Point

### `src/api/blueprints/chat.py`

---

#### `chat_route()` — POST /chat
Main entry point for all user messages.

**What it does:**
1. Reads `query` and `session_id` from request JSON
2. Runs `@require_api_key` and `@rate_limit` decorators before executing
3. Loads or creates session from DynamoDB
4. Builds LangChain message history from stored history
5. Constructs full `initial_state` including all flow state fields
6. Invokes `graph.invoke(initial_state)`
7. Extracts `structured_output` from result
8. Saves updated session + flow_state back to DynamoDB
9. Logs query telemetry
10. Returns `success(structured)` JSON response

**Calls:**
- `require_api_key` (decorator) → `src/api/middleware/auth.py`
- `rate_limit` (decorator) → `src/api/middleware/rate_limit.py`
- `get_session(thread_id)` → `src/services/session.py`
- `create_session(thread_id, client_id, agent_id)` → `src/services/session.py`
- `build_messages(raw_history)` → `src/services/session.py`
- `graph.invoke(initial_state, config)` → `src/agent/graph.py`
- `extract_flow_state(result)` → `src/services/session.py`
- `save_session(...)` → `src/services/session.py`
- `_log_query(...)` → local
- `success(structured)` → `src/api/schemas/responses.py`
- `error(code, message, status)` → `src/api/schemas/responses.py`

**Error handling:**
- `GraphRecursionError` → returns `error("agent_loop", ..., 500)`
- `OshaAgentError` → returns `error("agent_error", ..., 500)`
- `Exception` → returns `error("internal_error", ..., 500)`

---

#### `_log_query(client_id, agent_id, thread_id, query, structured)`
Writes query telemetry to DynamoDB. Fails silently — never raises.

**What it does:**
- If `structured.type == "search_results"` → joins result section IDs into a comma string
- If `structured.type == "generate_result"` → records section ID and marks `generation_invoked = "Y"`
- Writes one row to `DYNAMODB_TABLE_QUERY_LOGS`

**Calls:**
- `get_dynamodb_client()` → `src/services/aws.py`
- `settings.DYNAMODB_TABLE_QUERY_LOGS` → `src/config/settings.py`

---

## LAYER 2 — Middleware (Decorators on chat_route)

### `src/api/middleware/auth.py`

#### `require_api_key(f)`
Validates the `X-API-Key` header before the route handler runs.

**What it does:**
1. Reads `X-API-Key` from request headers
2. Looks up key in `DYNAMODB_TABLE_API_KEYS`
3. Checks `status == "active"` and optional domain allowlist
4. Attaches `request.client_id` and `request.agent_id` for use in the route

**Calls:**
- `get_dynamodb_client()` → `src/services/aws.py`
- `error(...)` → `src/api/schemas/responses.py`

---

### `src/api/middleware/rate_limit.py`

#### `rate_limit(f)`
Per-API-key sliding window rate limiter using Redis.

**What it does:**
1. Builds Redis key from `client_id`
2. Increments counter, sets expiry on first request
3. Returns `429` if count exceeds `REDIS_RATE_LIMIT_MAX`

**Calls:**
- `redis.from_url(settings.REDIS_URL)`
- `error(...)` → `src/api/schemas/responses.py`

---

## LAYER 3 — Session Management

### `src/services/session.py`

---

#### `get_session(session_id) → dict | None`
Reads session from DynamoDB.

**Returns:** `{session_id, client_id, agent_id, history: list, flow_state: dict}` or `None`

**Calls:**
- `get_dynamodb_client()` → `src/services/aws.py`
- `json.loads(...)` for history and flow_state fields

---

#### `create_session(session_id, client_id, agent_id) → str`
Creates a new empty session row in DynamoDB.

**Calls:**
- `get_dynamodb_client()` → `src/services/aws.py`
- `_now()`, `_ttl()` → local helpers

---

#### `save_session(session_id, client_id, agent_id, history, flow_state=None) → str`
Persists session to DynamoDB. Caps history to `SESSION_MAX_HISTORY * 2` messages.

**What it does:**
- Slices history to last N messages to prevent unbounded growth
- Serializes history and flow_state as JSON strings
- Writes full item with TTL

**Calls:**
- `get_dynamodb_client()` → `src/services/aws.py`
- `_now()`, `_ttl()` → local helpers

---

#### `build_messages(history) → list`
Converts stored history dicts into LangChain message objects.

**What it does:**
- If `len(history) <= 10`: converts each `{role, content}` to `HumanMessage` or `AIMessage`
- If `len(history) > 10`: summarizes older turns via LLM, keeps last 4 turns verbatim
  - Older turns → `SystemMessage("Conversation summary: ...")`
  - Recent turns → `HumanMessage` / `AIMessage`

**Calls:**
- `bedrock.invoke_raw(summary_prompt)` → `src/llm/bedrock.py` (only when history > 10)

---

#### `extract_flow_state(result) → dict`
Extracts flow state fields from graph result dict for persistence.

**What it does:**
- Reads all 8 flow fields from result with safe defaults
- If `stage == "done"`: resets to `stage="classify"`, clears `search_results`, `selected_section`, `rewritten_query`, `clarification_count`

**Calls:** Nothing (pure data extraction)

---

#### `_now() → str`
Returns current UTC ISO timestamp string.

#### `_ttl() → int`
Returns Unix timestamp of session expiry (`now + SESSION_TTL_SECONDS`).

---

## LAYER 4 — Agent Graph

### `src/agent/graph.py`

---

#### `build_graph() → StateGraph`
Assembles the LangGraph computation graph and compiles it.

**Graph structure:**
```
START → agent
agent → (should_continue) → tools | END
tools → extract_output
extract_output → (_after_extract) → agent | END
```

**Nodes:**
- `"agent"` → `agent()`
- `"tools"` → `ToolNode(all_tools)`
- `"extract_output"` → `extract_output()`

**Calls:**
- `StateGraph(AgentState)` → `src/agent/state.py`
- `ToolNode(all_tools)` → `src/agent/tools/__init__.py`

---

#### `agent(state) → dict`
LLM node. Invokes the LLM with full message history.

**What it does:**
- Passes all messages in state to `_llm_with_tools`
- Returns `{"messages": [response]}`
- LLM decides whether to call a tool or respond directly

**Calls:**
- `_llm_with_tools.invoke(messages)` — ChatBedrockConverse bound with all_tools
- `debug_callback` → `src/agent/debug.py`

---

#### `should_continue(state) → str`
Routing function after `agent` node.

**Returns:** `"tools"` if last message has tool_calls, `END` otherwise

---

#### `extract_output(state) → dict`
Parses the last `ToolMessage` into `structured_output`.

**What it does:**
- Finds the last `ToolMessage` in message history
- If `search_regulations`: parses JSON → `structured_output`
- If `generate_answer`: parses JSON, adds `type="generate_result"` → `structured_output`
- If no tool message: returns `{"structured_output": None}`

---

#### `_after_extract(state) → str`
Routing function after `extract_output` node.

**Returns:** `END` if last tool was `generate_answer` (flow complete), `"agent"` otherwise (agent needs to present results to user)

---

#### `_build_system_prompt() → str`
Builds the full system prompt for the agent LLM at module load time.

**What it does:**
- Inlines `REGULATORY_PARTS` dict from registry
- Defines tool descriptions for `search_regulations` and `generate_answer`
- Defines 4-step workflow: Understand → Search → Present → Answer
- Defines strict rules (no memory, one search per turn, always verify through tools)

**Calls:**
- `REGULATORY_PARTS` → `src/agent/tools/registry.py`

---

#### `_build_llm() → ChatBedrockConverse`
Creates LLM instance bound with all tools.

**Calls:**
- `ChatBedrockConverse(...)` from `langchain_aws`
- `.bind_tools(all_tools)` → `src/agent/tools/__init__.py`
- `settings` → `src/config/settings.py`

---

## LAYER 5 — Agent State

### `src/agent/state.py`

#### `AgentState` (TypedDict)
Defines the full state schema passed through the graph.

| Field | Type | Purpose |
|---|---|---|
| `messages` | `Annotated[list, add_messages]` | Full conversation history, auto-merged |
| `structured_output` | `dict \| None` | Last tool result for API response |
| `stage` | `str` | Current workflow stage |
| `original_query` | `str` | First user query, never overwritten |
| `refined_query` | `str` | Query updated after clarification |
| `search_results` | `list` | Results from last search, persisted for user pick |
| `part_filter` | `str \| None` | CFR part filter after ambiguity resolved |
| `ambiguity_parts` | `list` | Parts list when results span multiple parts |
| `selected_section` | `str` | Section ID user selected |
| `rewritten_query` | `str` | Query rewritten for generate_answer |
| `clarification_count` | `int` | Clarification rounds asked (max 2) |

---

## LAYER 6 — Tools

### `src/agent/tools/__init__.py`

#### `all_tools`
List: `[search_regulations, generate_answer]`
Exported to `graph.py` for `bind_tools()` and `ToolNode`.

---

### `src/agent/tools/registry.py`

#### `REGULATORY_PARTS` (dict)
Maps CFR part numbers to human-readable descriptions.
Used in system prompt and ambiguity detection.

Examples: `"1910" → "General Industry"`, `"1926" → "Construction"`, `"1904" → "Recordkeeping"`

#### `get_cfr_part(section_id) → str | None`
Extracts CFR part from section ID (e.g. `"1926.451"` → `"1926"`).
Returns `None` if part not in `REGULATORY_PARTS`.

**Called by:** `_detect_ambiguity()`, `discover()` in `search_regulations.py`

---

### `src/agent/tools/search_regulations.py`

---

#### `search_regulations(query, part_filter=None)` — LangChain Tool
Top-level tool called by the agent LLM.

**What it does:**
- Wraps `discover()` in a try/except
- On `OshaNoResultsError`: returns `{"type": "search_no_results", "message": "..."}` as JSON string
- On success: returns `discover()` result as JSON string

**Calls:**
- `discover(query, part_filter)` → local

---

#### `discover(query, part_filter=None) → dict`
Core search logic.

**What it does:**
1. Calls `bedrock_kb.retrieve(query, top_k)` to get raw KB chunks
2. Parses section ID from each chunk's S3 source URI via `_parse_section_from_source()`
3. Deduplicates by section ID (keeps highest score per section)
4. Applies `part_filter` if provided
5. Raises `OshaNoResultsError` if no results after filtering
6. Calls `_detect_ambiguity(results)` to check if results span multiple parts
7. Returns dict: `{query, ambiguous, clarification_message, results: [{section, source, title, part, excerpt, score}]}`

**Calls:**
- `bedrock_kb.retrieve(query, top_k)` → `src/retrieval/bedrock_kb.py`
- `_parse_section_from_source(source)` → local
- `_detect_ambiguity(results)` → local
- `get_cfr_part(section_id)` → `src/agent/tools/registry.py`
- `REGULATORY_PARTS` → `src/agent/tools/registry.py`
- `OshaNoResultsError` → `src/exceptions/errors.py`

---

#### `_detect_ambiguity(results) → dict | None`
Checks if top search results span 2+ different CFR parts.

**Returns:** `{parts: [...], message: "..."}` if ambiguous, `None` if all results from same part

**Calls:**
- `get_cfr_part()` → `src/agent/tools/registry.py`
- `REGULATORY_PARTS` → `src/agent/tools/registry.py`

---

#### `_parse_section_from_source(source) → str`
Extracts section ID from S3 URI.

Example: `"s3://bucket/normalized/29_CFR_1926_451.txt"` → `"1926.451"`

Uses regex to match `29_CFR_{part}_{section}` pattern.

---

### `src/agent/tools/generate_answer.py`

---

#### `generate_answer(section, query)` — LangChain Tool
Top-level tool called by the agent LLM after user selects a section.

**What it does:**
1. Calls `bedrock_kb.retrieve_for_section(query, section, top_k=10)`
2. If no hits: returns NOT FOUND JSON immediately
3. Builds `context_text` from all hit texts joined with newlines
4. Constructs `user_message` with locked regulatory text + user question
5. Calls `bedrock.invoke(GENERATION_PROMPT, user_message)` → gets dict
6. Calls `_calculate_scores(answer, context_text, hits)`
7. Calls `_build_manager_citations(answer, section)`
8. Adds `type`, `section`, `source_uri` fields
9. Returns JSON string

**Calls:**
- `bedrock_kb.retrieve_for_section()` → `src/retrieval/bedrock_kb.py`
- `bedrock.invoke(GENERATION_PROMPT, user_message)` → `src/llm/bedrock.py`
- `_calculate_scores()` → local
- `_build_manager_citations()` → local
- `OshaGenerationError` → `src/exceptions/errors.py`

---

#### `_calculate_scores(answer, context_text, hits) → dict`
Computes quality scores for the generated answer.

**What it does:**
- `verbatim_percent`: % of bullets where at least one sentence is found word-for-word in source text
- `retrieval_score`: mean of top-3 KB chunk scores × 100
- `confidence_percent`: `0.70 × verbatim_percent + 0.30 × retrieval_score`
- Returns 0/0 for NOT FOUND IN SOURCE answers

**Calls:**
- `_normalize()` → local

---

#### `_build_manager_citations(answer, section) → list[dict]`
Builds citation list for the API response.

**What it does:**
- Primary section always added first
- Scans bullet citations for additional section IDs via regex `§(\d{4}\.\d+)`
- Deduplicates by section ID
- Returns `[{"section": "29 CFR §1926.454", "url": "https://www.osha.gov/..."}]`

**Calls:**
- `_build_osha_url(section)` → local

---

#### `_build_osha_url(section) → str`
Constructs the OSHA.gov regulation URL.

`"1926.451"` → `"https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.451"`

---

#### `_normalize(text) → str`
Cleans text for verbatim matching.
Replaces Unicode § characters, collapses whitespace, strips.

---

## LAYER 7 — LLM

### `src/llm/bedrock.py`

---

#### Pydantic Models

**`BulletPoint`**
- `text: str` — verbatim regulatory text
- `citations: List[str]` — CFR citation strings

**`GenerationOutput`**
- `summary: str`
- `bullets: List[BulletPoint]`
- `why: str`
- `disclaimer: str`

These are passed to `with_structured_output()` — Claude enforces the schema at the model level via tool calling API. No manual JSON parsing needed.

---

#### Module-level singletons
- `_llm` — `ChatBedrockConverse` instance
- `_structured_llm` — `_llm.with_structured_output(GenerationOutput)`

Created once at import time. Reused for all `invoke()` calls.

---

#### `invoke(system_prompt, user_message) → dict`
Structured LLM call for answer generation.

**What it does:**
- Sends `[SystemMessage, HumanMessage]` to `_structured_llm`
- Claude returns a validated `GenerationOutput` Pydantic object
- `.model_dump()` converts to plain dict
- Raises `OshaGenerationError` on any failure

**Calls:**
- `_structured_llm.invoke([SystemMessage, HumanMessage])`
- `OshaGenerationError` → `src/exceptions/errors.py`

**Called by:** `generate_answer()` in `src/agent/tools/generate_answer.py`

---

#### `invoke_raw(prompt) → str`
Plain text LLM call for session summarization.

**What it does:**
- Creates a fresh LLM instance (temperature=0.0, max_tokens=512)
- Returns raw string response

**Calls:**
- `ChatBedrockConverse(...).invoke([HumanMessage])`

**Called by:** `build_messages()` in `src/services/session.py`

---

#### `_build_llm() → ChatBedrockConverse`
Creates LLM instance from settings.

---

## LAYER 8 — Knowledge Base Retrieval

### `src/retrieval/bedrock_kb.py`

---

#### `retrieve(query, top_k=10) → list[dict]`
General KB search. No section filter.

**What it does:**
- Calls Bedrock `retrieve` API with hybrid search (`HYBRID` type)
- Filters results by minimum score (`BEDROCK_RETRIEVAL_MIN_SCORE`)
- Returns list of `{text, score, source}` dicts

**Calls:**
- `_get_client()` → local
- `settings.BEDROCK_KB_ID`, `settings.BEDROCK_RETRIEVAL_MIN_SCORE`

**Called by:** `discover()` in `src/agent/tools/search_regulations.py`

---

#### `retrieve_for_section(query, section, top_k=10) → list[dict]`
Section-filtered KB search for answer generation.

**What it does:**
1. Tries metadata filter on S3 source URI containing section key
2. If filtered results empty: falls back to client-side filtering on unfiltered results
3. If still empty: returns unfiltered results (caller handles NOT FOUND)

**Calls:**
- `_get_client()` → local
- `_section_to_s3_key(section)` → local
- `retrieve(query, top_k)` → local (fallback)

**Called by:** `generate_answer()` in `src/agent/tools/generate_answer.py`

---

#### `_section_to_s3_key(section) → str`
Converts section ID to S3 filename fragment.

`"1926.451"` → `"29_CFR_1926_451"`

---

#### `_get_client()`
Lazy-loads and caches the `bedrock-agent-runtime` boto3 client.

---

## LAYER 9 — Configuration

### `src/config/settings.py`

All values loaded from environment variables.

| Setting | Purpose |
|---|---|
| `AWS_REGION` | AWS region for all boto3 clients |
| `BEDROCK_MODEL_ID` | Claude model ID for LLM calls |
| `BEDROCK_TEMPERATURE` | LLM temperature (generation) |
| `BEDROCK_MAX_TOKENS` | Max tokens for generation |
| `BEDROCK_KB_ID` | Bedrock Knowledge Base ID |
| `BEDROCK_RETRIEVAL_TOP_K` | Max chunks returned from KB |
| `BEDROCK_RETRIEVAL_MIN_SCORE` | Minimum relevance score threshold |
| `DYNAMODB_TABLE_SESSIONS` | Table for session storage |
| `DYNAMODB_TABLE_API_KEYS` | Table for API key validation |
| `DYNAMODB_TABLE_QUERY_LOGS` | Table for query telemetry |
| `SESSION_TTL_SECONDS` | Session expiry in seconds |
| `SESSION_MAX_HISTORY` | Max conversation turns to keep |
| `REDIS_URL` | Redis connection for rate limiting |
| `REDIS_RATE_LIMIT_MAX` | Max requests per window |
| `ADMIN_API_KEY` | Admin key for internal routes |

#### `validate()`
Called at app startup. Raises `EnvironmentError` if required vars are missing.

---

## LAYER 10 — AWS Clients

### `src/services/aws.py`

#### `get_dynamodb_client()`
Returns `boto3` DynamoDB client. Uses `DYNAMODB_ENDPOINT_URL` override for local testing.

**Called by:** `auth.py`, `rate_limit.py`, `session.py`, `chat.py`

#### `get_bedrock_client()`
Returns `boto3` bedrock-runtime client.

---

## LAYER 11 — Exceptions

### `src/exceptions/errors.py`

All inherit from `OshaBaseError(Exception)`.

| Exception | Raised By | Caught By |
|---|---|---|
| `OshaGenerationError` | `bedrock.invoke()`, `bedrock.invoke_raw()` | `generate_answer()` tool, `build_messages()` |
| `OshaNoResultsError` | `discover()` | `search_regulations()` tool |
| `OshaAgentError` | (reserved) | `chat_route()` |
| `OshaAgentSessionError` | (reserved) | (not yet used) |
| `OshaIndexError` | (reserved) | (not yet used) |
| `OshaDocumentNotFoundError` | (reserved) | (not yet used) |

---

## LAYER 12 — Observability

### `src/agent/debug.py`

#### `AgentDebugCallback`
LangChain `BaseCallbackHandler` subclass. Singleton instance `debug_callback` used in `agent()` node.

All methods log at `DEBUG` level to `osha.agent.debug` logger.

| Method | Triggered When |
|---|---|
| `on_chat_model_start` | LLM receives messages |
| `on_llm_end` | LLM returns response |
| `on_llm_error` | LLM call fails |
| `on_tool_start` | Tool execution begins |
| `on_tool_end` | Tool returns result |
| `on_tool_error` | Tool raises exception |
| `on_chain_start` | LangGraph node starts |
| `on_chain_end` | LangGraph node finishes |

#### `_truncate(text, max_chars=300) → str`
Truncates long strings for log readability.

---

## Full Call Chain (one request, one generate_answer turn)

```
POST /chat
  require_api_key()         validates X-API-Key against DynamoDB
  rate_limit()              checks Redis counter
  chat_route()
    get_session()           reads DynamoDB
    build_messages()        converts history → LangChain messages
    graph.invoke()
      agent()               LLM decides → call generate_answer
      ToolNode              executes generate_answer tool
        generate_answer()
          retrieve_for_section()   queries Bedrock KB with section filter
          bedrock.invoke()
            _structured_llm        Claude returns GenerationOutput
          _calculate_scores()      verbatim + retrieval scoring
          _build_manager_citations()  OSHA.gov URLs
      extract_output()      parses ToolMessage → structured_output
    extract_flow_state()    reads stage/section/etc from result
    save_session()          writes DynamoDB
    _log_query()            writes DynamoDB (telemetry)
    success(structured)     returns JSON response
```
