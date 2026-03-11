import streamlit as st
import requests

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OSHA AI Assistant",
    page_icon="🦺",
    layout="centered",
)

# ── global styles ─────────────────────────────────────────────────────────────

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Configuration")
    api_base = st.text_input("API Base URL", value="http://localhost:5000")
    api_key  = st.text_input("X-API-Key", type="password")
    st.divider()
    st.caption("OSHA AI — Source-Verified Compliance Assistant")

# ── helpers ───────────────────────────────────────────────────────────────────
def headers():
    return {"X-API-Key": api_key, "Content-Type": "application/json"}

def do_chat(query, session_id=None):
    payload = {"query": query}
    if session_id:
        payload["session_id"] = session_id
    try:
        r = requests.post(f"{api_base}/chat", json=payload, headers=headers(), timeout=120)
        return r.json(), r.status_code
    except Exception as e:
        return {"error": str(e)}, 500


def render_search_results(body: dict):
    results = body.get("results", [])
    query   = body.get("query", "")

    st.markdown(f"**Search results for:** _{query}_")

    if body.get("ambiguous") and body.get("clarification"):
        st.warning(body["clarification"])
        return

    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        score_pct = int(score * 100) if score <= 1 else int(score)
        if score_pct >= 80:
            badge = "🟢 High"
        elif score_pct >= 50:
            badge = "🟡 Medium"
        else:
            badge = "🔴 Low"

        section   = r.get("section", "")
        title     = r.get("title", "Untitled")
        osha_url  = r.get("osha_url", "")
        raw       = r.get("excerpt", "")
        # Strip normalized file header (Source/Title/Section/Path lines) — show only regulation text
        import re as _re
        m = _re.search(r'(\r\n|\r|\n)\s*(\r\n|\r|\n)', raw)
        excerpt   = raw[m.end():].strip() if m and raw[m.end():].strip() else raw

        with st.expander(f"{i}. {section} — {title}", expanded=i == 1):
            col1, col2 = st.columns([3, 1])
            with col1:
                if osha_url:
                    st.markdown(f"[View on OSHA.gov]({osha_url})")
            with col2:
                st.caption(f"{badge} ({score_pct}%)")
            st.markdown(excerpt)

    st.info("Reply with a number (e.g. **1**) or section ID to get the full answer.")


def render_generate_result(body: dict):
    title           = body.get("title", "")
    ans_body        = body.get("body", "")
    conf            = body.get("confidence_percent", 0)
    verbatim        = body.get("verbatim_percent", 0)
    references      = body.get("references", [])
    not_found       = body.get("not_found", False)
    disclaimer      = body.get("disclaimer", "")

    # NOT FOUND case
    if not_found or "NOT FOUND IN SOURCE" in ans_body:
        st.error("No relevant information found in the requested section(s).")
        return

    import re as _re
    formatted = _re.sub(r"\*\*(.+?)\*\*", r"*\1*", ans_body, flags=_re.DOTALL)
    st.markdown(f"### {title}")
    st.markdown(formatted)

    st.divider()

    # Scores
    if conf >= 80:
        st.success("High Confidence")
    elif conf >= 50:
        st.warning("Moderate Confidence")
    else:
        st.error("Low Confidence")

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Confidence")
        st.progress(conf / 100, text=f"{conf}%")
    with col2:
        st.caption("Verbatim")
        st.progress(verbatim / 100, text=f"{verbatim}%")

    # References
    if references:
        st.markdown("**Sources:**")
        for r in references:
            label = r.get("section", "")
            url   = r.get("url", "")
            if url:
                st.markdown(f"- [{label}]({url})")
            else:
                st.markdown(f"- {label}")

    if disclaimer:
        st.caption(f"_{disclaimer}_")


def render_message(msg: dict):
    with st.chat_message(msg["role"]):
        msg_type = msg.get("type")
        if msg["role"] == "assistant" and msg_type == "search_results":
            render_search_results(msg)
        elif msg["role"] == "assistant" and msg_type == "generate_result":
            render_generate_result(msg)
        else:
            st.markdown(msg.get("content", ""))


# ── session state ─────────────────────────────────────────────────────────────
if "session_id"   not in st.session_state: st.session_state.session_id   = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "pending"      not in st.session_state: st.session_state.pending      = None

# ── title ─────────────────────────────────────────────────────────────────────
st.title("🦺 OSHA AI Assistant")
st.caption("Describe your situation — the agent will find the right regulation for you.")

if not api_key:
    st.warning("Enter your X-API-Key in the sidebar to get started.")
    st.stop()

# ── reset button ──────────────────────────────────────────────────────────────
if st.button("New Conversation", use_container_width=True, disabled=not st.session_state.chat_history):
    st.session_state.session_id   = None
    st.session_state.chat_history = []
    st.rerun()

# ── chat history ──────────────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    render_message(msg)

# ── chat input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Describe your situation or ask a question...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    st.session_state.pending = user_input
    st.rerun()

if st.session_state.pending:
    query = st.session_state.pending
    st.session_state.pending = None

    with st.spinner("Thinking..."):
        data, status = do_chat(query, st.session_state.session_id)

    if status != 200:
        err_msg = data.get("message", str(data)) if isinstance(data, dict) else str(data)
        st.session_state.chat_history.append({"role": "assistant", "content": f"Error: {err_msg}"})
    else:
        body = data.get("data", data)
        st.session_state.session_id = body.get("session_id")
        msg_type = body.get("type", "message")

        if msg_type in ("search_results", "generate_result"):
            st.session_state.chat_history.append({"role": "assistant", **body})
        elif msg_type == "search_no_results":
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": body.get("message", "No results found."),
            })
        else:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": body.get("message", "No response."),
            })

    st.rerun()
