import streamlit as st
import requests

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OSHA AI Assistant",
    page_icon="🦺",
    layout="centered",
)

# ── sidebar: config ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Configuration")
    api_base  = st.text_input("API Base URL", value="http://localhost:5000")
    api_key   = st.text_input("X-API-Key", type="password")
    client_id = st.text_input("Client ID", value="demo_client")
    agent_id  = st.text_input("Agent ID",  value="demo_agent")
    st.divider()
    st.caption("OSHA AI — Phase 1 Demo")

# ── helpers ───────────────────────────────────────────────────────────────────
def headers():
    return {"X-API-Key": api_key, "Content-Type": "application/json"}

def post(endpoint, payload):
    try:
        r = requests.post(f"{api_base}{endpoint}", json=payload, headers=headers(), timeout=30)
        return r.json(), r.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def do_discover(query, part_filter=None):
    payload = {"query": query, "client_id": client_id, "agent_id": agent_id}
    if part_filter:
        payload["part_filter"] = part_filter
    return post("/discover", payload)

def do_generate(query):
    payload = {
        "query": query,
        "section_ids": st.session_state.locked_sections,
        "client_id": client_id,
        "agent_id": agent_id,
    }
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id
    data, status = post("/generate", payload)
    if status != 200:
        st.error(f"Generation failed: {data.get('error', {}).get('message', data)}")
        return None
    body = data.get("data", data)
    st.session_state.session_id = body.get("session_id")
    return body.get("answer", {})

def render_answer(answer):
    st.markdown(answer.get("answer", "No answer returned."))

    st.divider()

    display_pct            = answer.get("display_pct", 0)
    display_label          = answer.get("display_label", "")
    quote_verification_pct = answer.get("quote_verification_pct", 0)
    verbatim_coverage_pct  = answer.get("verbatim_coverage_pct", 0)

    if display_label == "Not Found":
        st.error("🔴 0% — Not Found in Source — consider locking a different section.")
    else:
        if display_label == "Exact Match":
            st.success(f"🟢 {display_pct}% — {display_label}")
        elif display_label == "Partial Match":
            st.warning(f"🟡 {display_pct}% — {display_label}")
        else:
            st.info(f"🟠 {display_pct}% — {display_label}")

        col1, col2 = st.columns(2)
        with col1:
            st.caption("Quote Verification")
            st.progress(quote_verification_pct / 100, text=f"{quote_verification_pct}%")
        with col2:
            st.caption("Verbatim Coverage")
            st.progress(verbatim_coverage_pct / 100, text=f"{verbatim_coverage_pct}%")

    if answer.get("verbatim_quotes"):
        with st.expander(f"Verbatim quotes from source ({len(answer['verbatim_quotes'])})"):
            for q in answer["verbatim_quotes"]:
                st.markdown(f"> {q}")

    if answer.get("sections_cited"):
        st.caption(f"Cited: {', '.join(answer['sections_cited'])}")
    st.caption(f"_{answer.get('disclaimer', '')}_")

# ── session state ─────────────────────────────────────────────────────────────
if "session_id"       not in st.session_state: st.session_state.session_id       = None
if "discover_results" not in st.session_state: st.session_state.discover_results  = []
if "locked_sections"  not in st.session_state: st.session_state.locked_sections   = []
if "chat_history"     not in st.session_state: st.session_state.chat_history      = []
if "last_query"       not in st.session_state: st.session_state.last_query        = ""
if "auto_send"        not in st.session_state: st.session_state.auto_send         = False
if "ambiguous"        not in st.session_state: st.session_state.ambiguous         = False
if "parts_found"      not in st.session_state: st.session_state.parts_found       = {}
if "part_filter"      not in st.session_state: st.session_state.part_filter       = None

# ── title ─────────────────────────────────────────────────────────────────────
st.title("🦺 OSHA AI Assistant")
st.caption("Powered by BM25 + Claude on AWS Bedrock")

if not api_key:
    st.warning("Enter your X-API-Key in the sidebar to get started.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — DISCOVER
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Step 1 — Search Regulations")

with st.form("discover_form"):
    query = st.text_input(
        "Your question",
        value=st.session_state.last_query,
        placeholder="e.g. What are the fall protection requirements for workers?",
    )
    submitted = st.form_submit_button("Search", use_container_width=True)

if submitted and query:
    st.session_state.last_query      = query
    st.session_state.locked_sections = []
    st.session_state.session_id      = None
    st.session_state.chat_history    = []
    st.session_state.auto_send       = False
    st.session_state.ambiguous       = False
    st.session_state.parts_found     = {}
    st.session_state.discover_results = []
    st.session_state.part_filter     = None

    with st.spinner("Searching OSHA regulations..."):
        data, status = do_discover(query)

    if status != 200:
        st.error(f"Search failed: {data.get('error', {}).get('message', data)}")
    else:
        body = data.get("data", data)
        if body.get("ambiguous"):
            # block results — force part selection first
            st.session_state.ambiguous   = True
            st.session_state.parts_found = body.get("parts_labels", {})
        else:
            st.session_state.discover_results = body.get("results", [])

# ─────────────────────────────────────────────────────────────────────────────
# AMBIGUITY — force user to pick a CFR part before showing results
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.ambiguous:
    st.divider()
    st.warning("Your query matches regulations in **multiple regulatory parts**. Please clarify which applies to your situation:")

    cols = st.columns(len(st.session_state.parts_found))
    for col, (part, label) in zip(cols, st.session_state.parts_found.items()):
        with col:
            if st.button(f"**{part}**\n{label}", use_container_width=True, key=f"part_{part}"):
                st.session_state.ambiguous   = False
                st.session_state.part_filter = part

                with st.spinner(f"Searching {part} regulations..."):
                    data, status = do_discover(st.session_state.last_query, part_filter=part)

                if status != 200:
                    st.error(f"Search failed: {data.get('error', {}).get('message', data)}")
                else:
                    body = data.get("data", data)
                    st.session_state.discover_results = body.get("results", [])
                st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — LOCK A SECTION
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.discover_results:
    st.divider()
    st.subheader("Step 2 — Lock a Section")
    if st.session_state.part_filter:
        st.caption(f"Showing results for **29 CFR Part {st.session_state.part_filter}** — pick the most relevant section.")
    else:
        st.caption("Pick the most relevant section — your original question will be answered automatically.")

    for r in st.session_state.discover_results:
        score_color = "green" if r["relevance"] == "High" else ("orange" if r["relevance"] == "Medium" else "gray")
        with st.container(border=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"**{r['section_id']}** — {r['title']}")
                st.caption(f"Source: {r['source']}  |  Path: {r['path']}")
                st.markdown(f"> {r['excerpt']}")
            with col2:
                st.markdown(f":{score_color}[{r['relevance']}]")
                st.caption(f"{r['score']}")
                if st.button("Lock", key=f"lock_{r['section_id']}"):
                    st.session_state.locked_sections = [r["section_id"]]
                    st.session_state.auto_send = True
                    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — GENERATE / CHAT
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.locked_sections:
    st.divider()
    st.subheader("Step 3 — Ask & Follow Up")
    st.success(f"Locked: **{', '.join(st.session_state.locked_sections)}**")

    # auto-send original query on first lock
    if st.session_state.auto_send and st.session_state.last_query:
        st.session_state.auto_send = False
        original_q = st.session_state.last_query
        st.session_state.chat_history.append({"role": "user", "content": original_q})
        with st.chat_message("user"):
            st.markdown(original_q)
        with st.chat_message("assistant"):
            with st.spinner("Generating answer..."):
                answer = do_generate(original_q)
            if answer is not None:
                render_answer(answer)
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
    else:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    render_answer(msg["content"])
                else:
                    st.markdown(msg["content"])

    follow_up = st.chat_input("Ask a follow-up question...")
    if follow_up:
        st.session_state.chat_history.append({"role": "user", "content": follow_up})
        with st.chat_message("user"):
            st.markdown(follow_up)
        with st.chat_message("assistant"):
            with st.spinner("Generating answer..."):
                answer = do_generate(follow_up)
            if answer is not None:
                render_answer(answer)
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
