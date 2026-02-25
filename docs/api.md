# OSHA AI — API Reference

Base URL: `https://api.fedregs.ai` (or `http://localhost:5000` locally)

All endpoints except `/health` require the header:
```
X-API-Key: <embed_key>
```

---

## Storage Architecture

```
DynamoDB — osha_clients       ← client profiles
DynamoDB — osha_agents        ← agent profiles + allowed domains
DynamoDB — osha_api_keys      ← embed keys per client/agent
DynamoDB — osha_query_logs    ← every query logged (search + generate)
DynamoDB — osha_sessions      ← persistent session history (last 10 exchanges, TTL 24h)
Redis                         ← rate limiting only (request count per key per minute)
```

---

## Session History

Sessions allow follow-up questions within a conversation context.

- History is **persistent** — stored in DynamoDB, survives page refresh and server restart
- Capped at **last 10 exchanges** (10 user + 10 assistant messages = 20 messages max)
- Sessions auto-expire after **24 hours** of inactivity (DynamoDB TTL)
- Pass `session_id` on `/generate` calls to continue a session
- Omit `session_id` to start a fresh session — a new one is created and returned
- Sessions are scoped to `client_id` + `agent_id`
- **A single client can have unlimited concurrent sessions** — one per user, tab, or conversation

---

## Authentication

All keys are scoped to a `client_id` + `agent_id` pair.
Pass the key in the `X-API-Key` header on every request.

Rate limiting is enforced per key via Redis.
Exceeding the limit returns `429 Too Many Requests`.

---

## Endpoints

### GET /health

Check service availability. No auth required.

**Response**
```json
{
  "status": "ok",
  "timestamp": "2026-02-25T10:00:00Z"
}
```

---

### POST /discover

Keyword search (BM25) across OSHA regulatory documents.
Returns ranked excerpts with citations and source links.
Does **not** generate an answer — discovery only.

**Request**
```json
{
  "query": "fall protection requirements for scaffolding",
  "client_id": "nonprofit-abc",
  "agent_id": "agent-01",
  "part_filter": "1926"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `query` | Yes | The search query |
| `client_id` | Yes | Client identifier |
| `agent_id` | Yes | Agent identifier |
| `part_filter` | No | Filter by CFR part e.g. `"1926"`. Use after ambiguous response. |

**Response — unambiguous**
```json
{
  "query": "fall protection requirements for scaffolding",
  "ambiguous": false,
  "total_results": 5,
  "results": [
    {
      "section_id": "1926.451(g)(1)",
      "source": "29 CFR Part 1926",
      "title": "Scaffolds — Fall Protection",
      "path": "https://...",
      "score": 0.8741,
      "relevance": "High",
      "excerpt": "[...extract...]\nEach employee on a scaffold more than 10 feet...\n[...extract...]"
    }
  ],
  "next_step": "Reply with the section_id(s) you want to lock for a detailed compliance answer."
}
```

**Response — ambiguous**
```json
{
  "query": "fall protection",
  "ambiguous": true,
  "parts_found": ["1910", "1926"],
  "parts_labels": {
    "1910": "29 CFR Part 1910 (General Industry Standards)",
    "1926": "29 CFR Part 1926 (Construction Standards)"
  },
  "clarification": "Your query matches regulations in multiple regulatory parts...",
  "results": [...]
}
```

When `ambiguous: true`, call `POST /discover` again with `part_filter` to narrow results.

**Error responses**
| Code | Meaning |
|------|---------|
| 400 | Missing or empty query |
| 401 | Invalid or missing API key |
| 404 | No results found |
| 429 | Rate limit exceeded |

---

### POST /generate

Generate a compliance answer from locked section IDs.
AI generation is only allowed after caller provides locked section IDs from a prior `/discover` call.

Optionally pass a `session_id` to continue a conversation with prior context.
History is capped at the last 10 exchanges.

**Request**
```json
{
  "query": "fall protection requirements for scaffolding",
  "section_ids": ["1926.451(g)(1)", "1926.451(g)(2)"],
  "client_id": "nonprofit-abc",
  "agent_id": "agent-01",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `query` | Yes | The user question |
| `section_ids` | Yes | Locked section IDs from `/discover` |
| `client_id` | Yes | Client identifier |
| `agent_id` | Yes | Agent identifier |
| `session_id` | No | Omit to start a new session. Pass to continue existing session. |

**Response**
```json
{
  "query": "fall protection requirements for scaffolding",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "locked_section_ids": ["1926.451(g)(1)", "1926.451(g)(2)"],
  "generation_invoked": true,
  "answer": {
    "answer": "Each employee on a scaffold more than 10 feet (3.1 m) above a lower level shall be protected from falling to that lower level.",
    "sections_cited": ["1926.451(g)(1)"],
    "verbatim_quotes": [
      "Each employee on a scaffold more than 10 feet (3.1 m) above a lower level shall be protected from falling to that lower level."
    ],
    "confidence": "Exact match",
    "confidence_score": 0.97,
    "verbatim_score": 1.0,
    "disclaimer": "This information is retrieved from official OSHA documentation. For legal compliance decisions, consult a certified safety professional or contact OSHA directly at osha.gov or 1-800-321-OSHA."
  }
}
```

**Error responses**
| Code | Meaning |
|------|---------|
| 400 | Missing query or section_ids |
| 401 | Invalid or missing API key |
| 404 | section_ids not found in index |
| 429 | Rate limit exceeded |
| 502 | Bedrock generation failed |

---

### POST /keys

Create a new embed key for a client/agent pair.
Requires admin key in `X-Admin-Key` header.

**Request**
```json
{
  "client_id": "nonprofit-abc",
  "agent_id": "agent-01",
  "allowed_domains": ["nonprofitabc.org"]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `client_id` | Yes | Client identifier |
| `agent_id` | Yes | Agent identifier |
| `allowed_domains` | No | If set, only requests from these origins are allowed |

**Response**
```json
{
  "embed_key": "osha_live_abc123xyz",
  "client_id": "nonprofit-abc",
  "agent_id": "agent-01",
  "created_at": "2026-02-25T10:00:00Z"
}
```

---

### POST /keys/rotate

Revoke the current key and issue a new one instantly.
Old key stops working immediately.
Requires admin key in `X-Admin-Key` header.

**Request**
```json
{
  "client_id": "nonprofit-abc",
  "agent_id": "agent-01"
}
```

**Response**
```json
{
  "embed_key": "osha_live_newkey456",
  "client_id": "nonprofit-abc",
  "agent_id": "agent-01",
  "rotated_at": "2026-02-25T11:00:00Z"
}
```

---

### DELETE /keys/{embed_key}

Permanently revoke a key.
Requires admin key in `X-Admin-Key` header.

**Response**
```json
{
  "revoked": true,
  "embed_key": "osha_live_abc123xyz"
}
```

---

### GET /logs

Export query logs for a client.
Requires admin key in `X-Admin-Key` header.

**Query parameters**
| Param | Required | Description |
|-------|----------|-------------|
| `client_id` | Yes | Filter by client |
| `from` | No | ISO 8601 start date e.g. `2026-01-01` |
| `to` | No | ISO 8601 end date e.g. `2026-02-01` |
| `limit` | No | Max records returned (default 100) |

**Example**
```
GET /logs?client_id=nonprofit-abc&from=2026-01-01&to=2026-02-01
```

**Response**
```json
{
  "client_id": "nonprofit-abc",
  "total": 42,
  "logs": [
    {
      "log_id": "uuid",
      "client_id": "nonprofit-abc",
      "agent_id": "agent-01",
      "timestamp": "2026-01-15T09:23:00Z",
      "query": "fall protection scaffolding",
      "returned_section_ids": ["1926.451(g)(1)", "1926.451(g)(2)"],
      "locked_section_ids": ["1926.451(g)(1)"],
      "generation_invoked": true
    }
  ]
}
```

---

## Error Format

All errors follow this shape:

```json
{
  "error": "no_results",
  "message": "No results found for query: 'xyz'",
  "status": 404
}
```

---

## Full Flow

```
Client
  │
  ├─ POST /discover ────────────────► BM25 search
  │      │                                │
  │   ambiguous?                     ranked results
  │      │ yes                            │
  │   POST /discover (part_filter)   user reviews
  │                                        │
  ├─ POST /generate ────────────────► load session history (DynamoDB)
  │   + session_id                         │
  │                                   Bedrock LLM (history capped at 10)
  │                                        │
  │                                   save updated history (DynamoDB)
  │                                        │
  │                                   answer + scores + session_id
  │
  └─ every request logged to DynamoDB osha_query_logs
```

---

## DynamoDB Tables

### osha_clients
| Field | Type | Notes |
|-------|------|-------|
| `client_id` | String (PK) | Unique client identifier |
| `name` | String | Organization name |
| `email` | String | Contact email |
| `status` | String | active \| suspended |
| `created_at` | String | ISO timestamp |

### osha_agents
| Field | Type | Notes |
|-------|------|-------|
| `agent_id` | String (PK) | Unique agent identifier |
| `client_id` | String | Owner client |
| `name` | String | Agent name e.g. "Safety Widget" |
| `allowed_domains` | List | Optional domain allowlist e.g. ["nonprofitabc.org"] |
| `status` | String | active \| suspended |
| `created_at` | String | ISO timestamp |

### osha_api_keys
| Field | Type | Notes |
|-------|------|-------|
| `embed_key` | String (PK) | The API key |
| `client_id` | String | Owner client |
| `agent_id` | String | Owner agent |
| `allowed_domains` | List | Optional domain allowlist |
| `created_at` | String | ISO timestamp |
| `active` | Boolean | False = revoked |

### osha_query_logs
| Field | Type | Notes |
|-------|------|-------|
| `query_id` | String (PK) | UUID |
| `client_id` | String | |
| `agent_id` | String | |
| `timestamp` | String | ISO UTC |
| `query_text` | String | |
| `returned_section_ids` | String | Comma-joined |
| `locked_section_ids` | String | Comma-joined or empty |
| `generation_invoked` | String | Y or N |

### osha_sessions
| Field | Type | Notes |
|-------|------|-------|
| `session_id` | String (PK) | UUID |
| `client_id` | String | |
| `agent_id` | String | |
| `history` | String | JSON string, last 10 exchanges |
| `created_at` | String | ISO timestamp |
| `updated_at` | String | ISO timestamp |
| `ttl` | Number | Unix timestamp — DynamoDB auto-deletes after 24h |
