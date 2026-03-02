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
    api_base = st.text_input("API Base URL", value="http://localhost:5000")
    api_key  = st.text_input("X-API-Key", type="password")
    st.divider()
    st.caption("OSHA AI — Agentic Mode")

# ── helpers ───────────────────────────────────────────────────────────────────
def headers():
    return {"X-API-Key": api_key, "Content-Type": "application/json"}

def do_chat(query, session_id=None):
    payload = {"query": query}
    if session_id:
        payload["session_id"] = session_id
    try:
        r = requests.post(f"{api_base}/chat", json=payload, headers=headers(), timeout=60)
        return r.json(), r.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def render_answer(answer):
    st.markdown(answer.get("answer", "No answer returned."))
    st.divider()

    display_pct            = answer.get("display_pct", 0)
    display_label          = answer.get("display_label", "")
    quote_verification_pct = answer.get("quote_verification_pct", 0)
    verbatim_coverage_pct  = answer.get("verbatim_coverage_pct", 0)

    if display_label == "Not Found":
        st.error("🔴 0% — Not Found in Source")
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
if "session_id"    not in st.session_state: st.session_state.session_id    = None
if "chat_history"  not in st.session_state: st.session_state.chat_history  = []
if "waiting"       not in st.session_state: st.session_state.waiting       = False

# ── title ─────────────────────────────────────────────────────────────────────
st.title("🦺 OSHA AI Assistant")
st.caption("Describe your situation — the agent will find the right regulation for you.")

if not api_key:
    st.warning("Enter your X-API-Key in the sidebar to get started.")
    st.stop()

# ── reset button ──────────────────────────────────────────────────────────────
if st.session_state.chat_history:
    if st.button("New Conversation", use_container_width=True):
        st.session_state.session_id   = None
        st.session_state.chat_history = []
        st.session_state.waiting      = False
        st.rerun()

# ── chat history display ───────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and isinstance(msg["content"], dict):
            render_answer(msg["content"])
        else:
            st.markdown(msg["content"])

# ── chat input ─────────────────────────────────────────────────────────────────
placeholder = "Reply here..." if st.session_state.waiting else "Describe your situation or ask a question..."
user_input = st.chat_input(placeholder)

if user_input:
    # Show user message immediately
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Call /chat
    with st.spinner("Thinking..."):
        data, status = do_chat(user_input, st.session_state.session_id)

    if status != 200:
        if isinstance(data, dict):
            err_msg = data.get("error", {}).get("message", str(data))
        else:
            err_msg = str(data)
        st.session_state.chat_history.append({"role": "assistant", "content": f"Error: {err_msg}"})
        with st.chat_message("assistant"):
            st.error(f"Error: {err_msg}")
    else:
        body = data.get("data", data)
        st.session_state.session_id = body.get("session_id")
        response_type = body.get("type")

        if response_type == "clarification":
            # Agent is asking a follow-up question
            message = body.get("message", "Can you provide more details?")
            st.session_state.waiting = True
            st.session_state.chat_history.append({"role": "assistant", "content": message})
            with st.chat_message("assistant"):
                st.markdown(message)

        elif response_type == "answer":
            # Final answer received
            st.session_state.waiting = False
            answer = body.get("answer", {})
            section_used = body.get("section_used", "")
            if section_used:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Section used: **{section_used}**"
                })
                with st.chat_message("assistant"):
                    st.markdown(f"Section used: **{section_used}**")
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            with st.chat_message("assistant"):
                render_answer(answer)

        else:
            st.session_state.chat_history.append({"role": "assistant", "content": str(body)})
            with st.chat_message("assistant"):
                st.markdown(str(body))
