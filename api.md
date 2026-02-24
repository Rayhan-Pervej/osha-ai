# OSHA AI — API Reference

Base URL: `https://api.fedregs.ai` (or `http://localhost:8000` locally)

All endpoints except `/health` require the header:
```
X-API-Key: <embed_key>
```

---

## Authentication

All keys are scoped to a `client_id` + `agent_id` pair. Pass the key in the `X-API-Key` header on every request.

Rate limiting is enforced per key. Exceeding the limit returns `429 Too Many Requests`.

---

## Endpoints

### GET /health

Check service availability. No auth required.

**Response**
```json
{
  "status": "ok"
}
```

---

### POST /discover

Keyword search (BM25) across OSHA regulatory documents. Returns ranked excerpts with citations. Does **not** generate an answer.

**Request**
```json
{
  "query": "fall protection requirements for scaffolding",
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01"
}
```

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
      "path": "1926/1926.451",
      "score": 0.8741,
      "relevance": "High",
      "excerpt": "Each employee on a scaffold more than 10 feet above..."
    }
  ],
  "next_step": "Reply with the section_id(s) you want to lock for a detailed compliance answer."
}
```

**Response — ambiguous (multiple CFR parts matched)**
```json
{
  "query": "fall protection",
  "ambiguous": true,
  "parts_found": ["1910", "1926"],
  "parts_labels": {
    "1910": "29 CFR Part 1910 (General Industry Standards)",
    "1926": "29 CFR Part 1926 (Construction Standards)"
  }
}
```

When `ambiguous: true`, call `POST /discover` again with `part_filter` to narrow results.

**Request with part_filter**
```json
{
  "query": "fall protection",
  "part_filter": "1926",
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01"
}
```

**Error responses**
| Code | Meaning |
|------|---------|
| 400  | Missing or empty query |
| 404  | No results found |
| 401  | Invalid or missing API key |
| 429  | Rate limit exceeded |

---

### POST /generate

Generate a compliance answer from locked section IDs. AI generation is only allowed after the caller provides locked section IDs from a prior `/discover` call.

**Request**
```json
{
  "query": "fall protection requirements for scaffolding",
  "section_ids": ["1926.451(g)(1)", "1926.451(g)(2)"],
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01"
}
```

**Response**
```json
{
  "query": "fall protection requirements for scaffolding",
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
| 400  | Missing query or section_ids |
| 401  | Invalid or missing API key |
| 422  | section_ids not found in index |
| 429  | Rate limit exceeded |
| 502  | Bedrock generation failed |

---

### POST /keys

Create a new embed key for a client/agent pair. Requires admin credentials (separate `X-Admin-Key` header).

**Request**
```json
{
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01",
  "allowed_domains": ["nonprofitabc.org"]
}
```

`allowed_domains` is optional. If provided, requests from other `Origin` headers are rejected.

**Response**
```json
{
  "embed_key": "osha_live_abc123xyz",
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01",
  "created_at": "2026-02-24T10:00:00Z"
}
```

---

### POST /keys/rotate

Revoke the current key and issue a new one. Old key stops working immediately.

**Request**
```json
{
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01"
}
```

**Response**
```json
{
  "embed_key": "osha_live_newkey456",
  "client_id": "nonprofit-abc",
  "agent_id":  "agent-01",
  "rotated_at": "2026-02-24T11:00:00Z"
}
```

---

### DELETE /keys/{embed_key}

Permanently revoke a key.

**Response**
```json
{
  "revoked": true,
  "embed_key": "osha_live_abc123xyz"
}
```

---

### GET /logs

Export query logs for a client. Requires admin credentials (`X-Admin-Key` header).

**Query parameters**
| Param | Required | Description |
|-------|----------|-------------|
| `client_id` | Yes | Filter by client |
| `from` | No | ISO 8601 start date e.g. `2026-01-01` |
| `to` | No | ISO 8601 end date e.g. `2026-02-01` |
| `limit` | No | Max records (default 100) |

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

## Error format

All errors follow this shape:

```json
{
  "error": "no_results",
  "message": "No results found for query: 'xyz'",
  "status": 404
}
```

---

## Flow diagram

```
Client
  │
  ├─ POST /discover ──────────────────► BM25 search
  │        │                                │
  │   ambiguous?                       ranked results
  │        │ yes                            │
  │   POST /discover (part_filter)     user reviews
  │                                         │
  ├─ POST /generate (locked section_ids) ──► Bedrock LLM
  │                                         │
  │                                    answer + scores
  │
  └─ query logged to DynamoDB automatically
```
