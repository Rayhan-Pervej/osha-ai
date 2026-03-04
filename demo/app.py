import re
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


def parse_metadata(text: str) -> tuple[str, dict | None]:
    """Split agent message into (answer_text, metadata_dict).

    Looks for the --- separator block that generate_answer appends.
    Returns (full_text, None) if no metadata block found.
    """
    # Match the metadata block starting with ---\nSection used:
    pattern = re.compile(
        r"\n\n---\n"
        r"Section used: (?P<section>[^\n]+)\n"
        r"Confidence: (?P<conf>\d+)%\n"
        r"Verbatim: (?P<verbatim>\d+)%"
        r"(?P<rest>.*)",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return text, None

    answer_text = text[: m.start()]
    confidence_pct = int(m.group("conf"))
    verbatim_pct = int(m.group("verbatim"))
    rest = m.group("rest")

    # Parse disclaimer (first non-empty line after scores)
    disclaimer = ""
    for line in rest.splitlines():
        line = line.strip()
        if line:
            disclaimer = line
            break

    if confidence_pct >= 90:
        label = "Exact Match"
    elif confidence_pct >= 50:
        label = "Partial Match"
    else:
        label = "Keyword Match"

    meta = {
        "section": m.group("section").strip(),
        "confidence_pct": confidence_pct,
        "verbatim_pct": verbatim_pct,
        "display_label": label,
        "disclaimer": disclaimer,
    }
    return answer_text, meta


def render_search_results(search: dict):
    results = search.get("results", [])
    query = search.get("query", "")
    st.markdown(f"**Search results for:** _{query}_")

    if search.get("ambiguous") and search.get("clarification"):
        st.warning(search["clarification"])

    for i, r in enumerate(results, 1):
        part_label = r.get("part_label", "")
        large_badge = " 🔶 Large" if r.get("large") else ""
        relevance_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(r["relevance"], "⚪")

        with st.expander(f"{i}. {r['section_id']} — {r.get('title', 'Untitled')}{large_badge}", expanded=i == 1):
            st.caption(f"{relevance_color} {r['relevance']} ({r['score']:.0%})  ·  {part_label}")
            st.markdown(r.get("excerpt", ""))


def render_message(msg: dict):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("search"):
            render_search_results(msg["search"])
        elif msg["role"] == "assistant" and msg.get("meta"):
            meta = msg["meta"]
            st.markdown(msg["content"])
            st.divider()

            label = meta["display_label"]
            conf  = meta["confidence_pct"]
            verb  = meta["verbatim_pct"]

            if label == "Not Found":
                st.error("🔴 Not Found in Source")
            elif label == "Exact Match":
                st.success(f"🟢 {label}")
            elif label == "Partial Match":
                st.warning(f"🟡 {label}")
            else:
                st.info(f"🟠 {label}")

            col1, col2 = st.columns(2)
            with col1:
                st.caption("Confidence")
                st.progress(conf / 100, text=f"{conf}%")
            with col2:
                st.caption("Verbatim")
                st.progress(verb / 100, text=f"{verb}%")

            st.caption(f"Section: `{meta['section']}`")
            if meta["disclaimer"]:
                st.caption(f"_{meta['disclaimer']}_")
        else:
            st.markdown(msg["content"])


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

# ── chat history display ──────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    render_message(msg)

# ── chat input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Describe your situation or ask a question...")

if user_input:
    # Save user message and mark as pending, then rerun to show it immediately
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

        if msg_type == "search_results":
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": None,
                "search": body,
            })
        elif msg_type == "search_no_results":
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": body.get("message", "No results found."),
                "meta": None,
            })
        else:
            message = body.get("message", "No response.")
            answer_text, meta = parse_metadata(message)
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": answer_text,
                "meta": meta,
            })

    st.rerun()
