# OSHA AI Assistant

A compliance research tool for nonprofit organizations. Ask questions about OSHA regulations in plain English — get answers pulled directly from the official regulatory text, with source citations.

---

## What it does

You type a question like *"What are the fall protection requirements for construction workers?"* and the system finds the relevant regulation, pulls the exact text, and gives you a direct answer — no hallucinations, no guessing. Every answer is traced back to specific OSHA sections.

Under the hood it runs BM25 (a search algorithm used in production search engines) against a local index of OSHA regulations, then sends the most relevant chunks to Claude on AWS Bedrock to generate the answer. The UI shows you a confidence score and actual verbatim quotes from the source so you can verify the answer yourself.

---

## Requirements

- Python 3.11+
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- AWS Bedrock access with Claude enabled in your region
- DynamoDB tables (created by setup script)

---

## Setup

**1. Clone and install dependencies**

```bash
git clone <repo-url>
cd osha-ai
pip install -r requirements.txt
```

**2. Set up environment variables**

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
DYNAMODB_TABLE_PREFIX=osha_ai
API_KEY_SECRET=your-secret-key-here
API_CORS_ORIGINS=["http://localhost:8501"]
```

**3. Create DynamoDB tables**

```bash
python scripts/setup_tables.py
```

This creates the tables for API keys and query logs. Only needs to run once.

**4. Start the API server**

```bash
python run.py
```

**5. Create an API key**

```bash
curl -X POST http://localhost:5000/keys \
  -H "Content-Type: application/json" \
  -d '{"client_id": "demo_client", "agent_id": "demo_agent"}'
```

Copy the `api_key` from the response — you'll need it for the UI.

On Windows PowerShell:

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/keys" -Method POST `
  -ContentType "application/json" `
  -Body '{"client_id": "demo_client", "agent_id": "demo_agent"}'
```

---

## Running the demo UI

```bash
streamlit run demo/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

In the sidebar, paste your API key and you're good to go.

---

## Running from the command line

If you prefer a terminal interface:

```bash
python main.py
```

Same workflow — search, pick a section, get an answer. Useful for quick tests without spinning up the UI.

---

## How the workflow works

1. **Search** — type your question and hit Search. The system ranks every OSHA section by relevance.
2. **Pick a section** — you'll see the top results with a short excerpt. Click Lock on the one that looks right.
3. **Get an answer** — the system automatically sends your question with the full section text to Claude. You get a direct answer with confidence score and verbatim quotes.
4. **Follow up** — ask follow-up questions in the chat box. The session keeps context across turns.

If your question could apply to both general industry (29 CFR Part 1910) and construction (29 CFR Part 1926), the system will ask you to clarify before showing results.

---

## Confidence scores explained

Every answer shows two scores:

- **Quote Verification** — what percentage of the quotes the model cited actually appear word-for-word in the source text. 100% means every quote checks out.
- **Verbatim Coverage** — what fraction of the answer is made up of verified source quotes. Higher means the answer is closer to the original regulatory language.

A green badge means exact match. Yellow means partial. Orange means keyword match — the right section was found but the answer required combining information from multiple places.

---

## Project structure

```
osha-ai/
├── src/
│   ├── api/            # Flask REST API
│   ├── rag/            # Discover + generate pipeline
│   ├── retrieval/      # BM25 index and chunk retrieval
│   ├── llm/            # Bedrock client
│   └── processors/     # Document chunking
├── data/
│   └── processed/      # chunks.json — the BM25 index
├── demo/
│   └── app.py          # Streamlit UI
├── scripts/
│   └── setup_tables.py # DynamoDB setup
└── main.py             # CLI interface
```

---

## Troubleshooting

**"ResourceNotFoundException" on startup** — run `python scripts/setup_tables.py` to create the DynamoDB tables.

**"Unable to connect to API"** — make sure the Flask server is running on port 5000 before opening the UI.

**Answers say "NOT FOUND IN SOURCE"** — the locked section doesn't contain the answer to your specific question. Try locking a different section from the search results.

**Streamlit UI is blank / not loading** — check that you've entered your API key in the sidebar.
