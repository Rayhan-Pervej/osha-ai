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
    st.caption("OSHA AI — Agentic Mode (Tool-Calling)")

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

# ── session state ─────────────────────────────────────────────────────────────
if "session_id"    not in st.session_state: st.session_state.session_id    = None
if "chat_history"  not in st.session_state: st.session_state.chat_history  = []

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
        st.rerun()

# ── chat history display ─────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── chat input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Describe your situation or ask a question...")

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
        message = body.get("message", "No response.")

        st.session_state.chat_history.append({"role": "assistant", "content": message})
        with st.chat_message("assistant"):
            st.markdown(message)
