"""Public web chat for the AI Health Coach (Streamlit).  Run:  streamlit run web_chat.py
Same agent as the Telegram bot: DeepSeek reasons + calls tools; RAG (ChromaDB) supplies each customer's memory."""
import json
import os
import re
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

if sqlite3.sqlite_version_info < (3, 35):  # ChromaDB needs SQLite >= 3.35; use the bundled build on older hosts
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
# Hosted settings: Streamlit Cloud "Secrets" -> environment variables (no-op locally / when already set).
try:
    for _k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "AGENT_MODEL", "AGENT_DAILY_LIMIT", "GLOBAL_DAILY_LIMIT", "HC_TZ"):
        if _k not in os.environ and _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # noqa: BLE001 - no secrets file configured
    pass
# Hosts with a read-only app folder: keep customer data in a temp dir instead.
try:
    _probe = Path(__file__).parent / "data" / ".write_test"
    _probe.write_text("1")
    _probe.unlink()
except OSError:
    os.environ.setdefault("HC_DATA_DIR", str(Path(tempfile.gettempdir()) / "hc-data"))
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# If the hc/ code folder did not make it to the host (web uploads often drop folders), unpack it from hc_bundle.zip.
_BUNDLE = _ROOT / "hc_bundle.zip"
if not (_ROOT / "hc").is_dir() and _BUNDLE.exists():
    import zipfile
    _dst = Path(tempfile.gettempdir()) / "hc_bundle"
    if not (_dst / "hc").is_dir():
        with zipfile.ZipFile(_BUNDLE) as _z:
            _z.extractall(_dst)
    sys.path.insert(0, str(_dst))
try:
    from hc import agent, calc, db  # noqa: E402
except Exception as _e:  # noqa: BLE001 - show the real reason on the page (hosts hide tracebacks from visitors)
    import traceback
    st.error(f"Startup problem: {type(_e).__name__}: {_e}")
    st.write("Files next to web_chat.py in this deployment:")
    st.code("\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in _ROOT.iterdir())))
    if (_ROOT / "hc").is_dir():
        st.write("Files inside hc/:")
        st.code("\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in (_ROOT / "hc").iterdir())))
    st.code(traceback.format_exc()[-1500:])
    st.stop()

st.set_page_config(page_title="AI Health Coach (RAG chatbot)", page_icon="🥗", layout="centered")
st.markdown("<style>.block-container{max-width:820px;padding-top:1.5rem}</style>", unsafe_allow_html=True)

SUGGESTIONS = ["Set up my profile", "I had 2 roti and 1 katori dal for lunch", "Remember that I dislike bhindi",
               "What should I eat for dinner?", "How am I doing today?"]


def session_id() -> str:
    """One private customer id per browser session, kept in the URL (?s=...) so a refresh resumes the same chat."""
    s = st.query_params.get("s", "")
    if not re.fullmatch(r"[a-f0-9]{12}", s):
        s = uuid.uuid4().hex[:12]
        st.query_params["s"] = s
    return s


uid = session_id()
if "msgs" not in st.session_state:
    with db.use_user(uid):
        st.session_state.msgs = [{"role": m["role"], "content": m["text"]} for m in db.get_chat(40)]

with st.sidebar:
    st.header("🥗 AI Health Coach")
    st.caption("A RAG chatbot for Indian diets: DeepSeek (LLM) + ChromaDB (vector memory) + deterministic nutrition tools.")
    st.markdown("**How RAG is used**\n1. Your notes, recent meals & weight are embedded into a private vector store.\n"
                "2. Before a recommendation the agent *retrieves* the most relevant memories and diet/allergy-safe reference foods.\n"
                "3. DeepSeek *generates* the answer from that context. Numbers come from code, not the LLM.")
    with db.use_user(uid):
        notes = db.get_notes()
    st.markdown("**What I remember about you**")
    for n in notes:
        st.caption(f"• {n['kind']}: {n['text']}")
    if not notes:
        st.caption("Nothing yet - try: *Remember that I dislike bhindi*")
    st.divider()
    st.caption(f"Your private session: `{uid}` (bookmark this page's URL to continue later).")
    if st.button("🗑 Delete my data & start over"):
        db.delete_user_data(uid)
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

st.title("AI Health Coach 🥗")
st.warning("Demo for learning. Not medical advice - don't enter real medical details. Messages are processed by the DeepSeek API. "
           + calc.DISCLAIMER.split(". Consult")[0] + ".", icon="⚠️")

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("trace"):
            with st.expander("🔎 How I answered (tools + retrieved memory)"):
                for t in m["trace"]:
                    st.markdown(f"**tool:** `{t['tool']}`")
                    if t["tool"] == "recommendation_context":
                        try:
                            ctx = json.loads(t["result"])
                            st.markdown("**Retrieved from your memory (RAG):**")
                            for x in ctx.get("remembered_notes_and_history", []) or ["(nothing relevant yet)"]:
                                st.caption(f"• {x}")
                            st.markdown("**Diet/allergy-safe reference foods retrieved:**")
                            st.caption("; ".join(f.split(" (")[0] for f in ctx.get("diet_safe_reference_foods", [])) or "-")
                        except ValueError:
                            st.code(t["result"][:600])
                    else:
                        st.code((t["args"] or "")[:300])

if not st.session_state.msgs:
    st.info("Hi! I'm your AI health coach for Indian food. Tell me about yourself to get started, or try a suggestion:")
    cols = st.columns(2)
    for i, s in enumerate(SUGGESTIONS):
        if cols[i % 2].button(s, key=f"sg{i}", use_container_width=True):
            st.session_state.pending = s
            st.rerun()

prompt = st.chat_input("Tell me what you ate, ask for a meal idea, or set a goal...") or st.session_state.pop("pending", None)
if prompt:
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            trace: list = []
            reply = agent.respond(uid, prompt, trace=trace)
        st.markdown(reply)
    st.session_state.msgs.append({"role": "assistant", "content": reply, "trace": trace})
    st.rerun()
