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
        r"Quote verification: (?P<qv>\d+)%\n"
        r"Verbatim coverage: (?P<vc>\d+)%\n"
        r"Confidence: (?P<conf>[^\n]+)"
        r"(?P<rest>.*)",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return text, None

    answer_text = text[: m.start()]
    qv = int(m.group("qv"))
    vc = int(m.group("vc"))
    rest = m.group("rest")

    # Parse verbatim quotes
    quotes = re.findall(r"^> (.+)$", rest, re.MULTILINE)

    # Parse disclaimer (last non-empty line after quotes)
    disclaimer = ""
    for line in reversed(rest.splitlines()):
        line = line.strip()
        if line and not line.startswith(">") and not line.startswith("Verbatim"):
            disclaimer = line
            break

    display_pct = qv if qv > 0 else vc
    conf = m.group("conf").strip()
    if "Exact" in conf:
        label = "Exact Match"
    elif "Partial" in conf:
        label = "Partial Match"
    else:
        label = "Keyword Match"

    meta = {
        "section": m.group("section").strip(),
        "quote_verification_pct": qv,
        "verbatim_coverage_pct": vc,
        "display_pct": display_pct,
        "display_label": label,
        "confidence": conf,
        "verbatim_quotes": quotes,
        "disclaimer": disclaimer,
    }
    return answer_text, meta


def render_message(msg: dict):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("meta"):
            meta = msg["meta"]
            st.markdown(msg["content"])
            st.divider()

            label = meta["display_label"]
            pct   = meta["display_pct"]

            if label == "Not Found":
                st.error("🔴 0% — Not Found in Source")
            elif label == "Exact Match":
                st.success(f"🟢 {pct}% — {label}")
            elif label == "Partial Match":
                st.warning(f"🟡 {pct}% — {label}")
            else:
                st.info(f"🟠 {pct}% — {label}")

            col1, col2 = st.columns(2)
            with col1:
                st.caption("Quote Verification")
                st.progress(meta["quote_verification_pct"] / 100,
                            text=f"{meta['quote_verification_pct']}%")
            with col2:
                st.caption("Verbatim Coverage")
                st.progress(meta["verbatim_coverage_pct"] / 100,
                            text=f"{meta['verbatim_coverage_pct']}%")

            if meta["verbatim_quotes"]:
                with st.expander(f"Verbatim quotes from source ({len(meta['verbatim_quotes'])})"):
                    for q in meta["verbatim_quotes"]:
                        st.markdown(f"> {q}")

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
        if isinstance(data, dict):
            err_msg = data.get("error", {}).get("message", str(data))
        else:
            err_msg = str(data)
        st.session_state.chat_history.append({"role": "assistant", "content": f"Error: {err_msg}"})
    else:
        body = data.get("data", data)
        st.session_state.session_id = body.get("session_id")
        message = body.get("message", "No response.")

        answer_text, meta = parse_metadata(message)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer_text,
            "meta": meta,
        })

    st.rerun()
