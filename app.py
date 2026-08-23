import streamlit as st
from agent.agent import process_user_request
from memory.memory import init_db, save_message, load_messages, clear_session
from network.network_monitor import get_network_snapshot
from ledger.ledger import verify_chain
import os
import re
import uuid

def format_latex(text: str) -> str:
    """Converts \\[ ... \\] and \\( ... \\) LaTeX delimiters to Streamlit-compatible $$ $$ and $ $."""
    text = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text

st.set_page_config(page_title="Sovereign AI Workbench", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    .main-title { font-size: 2.2rem; font-weight: 700; color: #58a6ff; margin-bottom: 0; }
    .subtitle { color: #8b949e; font-size: 1rem; margin-top: 0; }
    .network-panel {
        background-color: #161b22; border: 1px solid #30363d;
        border-radius: 8px; padding: 16px; margin-bottom: 16px;
    }
    .status-clear { color: #3fb950; font-weight: 600; }
    .status-alert { color: #f85149; font-weight: 600; }
    div[data-testid="stChatMessage"] { background-color: #161b22; border-radius: 10px; padding: 8px; }
</style>
""", unsafe_allow_html=True)

init_db()
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = load_messages(st.session_state.session_id)
if "show_audit_panel" not in st.session_state:
    st.session_state.show_audit_panel = False

# ---- Header with toggle button ----
header_col, toggle_col = st.columns([5, 1])
with header_col:
    st.markdown('<p class="main-title">🛡️ Sovereign AI Workbench</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Secure, air-gapped agentic AI for industrial workflows — zero external calls.</p>', unsafe_allow_html=True)
with toggle_col:
    st.write("")  # vertical spacing
    if st.button("🔒 Audit Panel"):
        st.session_state.show_audit_panel = not st.session_state.show_audit_panel

# ---- Main layout: chat area + optional right panel ----
if st.session_state.show_audit_panel:
    chat_col, audit_col = st.columns([3, 1])
else:
    chat_col = st.container()
    audit_col = None

with chat_col:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(format_latex(message["content"]))

    uploaded_file = st.file_uploader("Upload an image or report (optional)", type=["png", "jpg", "jpeg", "pdf", "txt"])
    saved_path = None
    if uploaded_file is not None:
        saved_path = os.path.join("uploads", uploaded_file.name)
        os.makedirs("uploads", exist_ok=True)
        with open(saved_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Uploaded: {uploaded_file.name}")

    if prompt := st.chat_input("Ask the AI to write code, analyze an image, or create a report..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_message(st.session_state.session_id, "user", prompt)

        with st.spinner("Processing local AI task..."):
            response = process_user_request(
                prompt=prompt,
                image_path=saved_path,
                history=st.session_state.messages
            )

        st.session_state.messages.append({"role": "assistant", "content": response})
        save_message(st.session_state.session_id, "assistant", response)
        st.rerun()

# ---- Right-side audit panel (only rendered if toggled on) ----
if audit_col is not None:
    with audit_col:
        st.markdown("#### 🔒 Network Audit")
        snapshot = get_network_snapshot()
        if snapshot["external_count"] == 0:
            st.markdown('<p class="status-clear">✅ No external connections</p>', unsafe_allow_html=True)
        else:
            st.markdown(f'<p class="status-alert">⚠️ {snapshot["external_count"]} external connection(s)</p>', unsafe_allow_html=True)
            for conn in snapshot["external_connections"]:
                st.text(conn)
        st.metric("Bytes Sent", f"{snapshot['bytes_sent'] / 1024:.1f} KB")
        st.metric("Bytes Received", f"{snapshot['bytes_recv'] / 1024:.1f} KB")
        if st.button("🔄 Refresh"):
            st.rerun()

        st.markdown("---")
        st.markdown("#### 🔗 Action Ledger")
        chain_status = verify_chain()
        if chain_status["valid"]:
            st.markdown(f'<p class="status-clear">✅ {chain_status["entries_checked"]} entries verified</p>', unsafe_allow_html=True)
        else:
            st.markdown(f'<p class="status-alert">⚠️ Broken at entry {chain_status["broken_at"]}</p>', unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🗑️ Clear Session History"):
            clear_session(st.session_state.session_id)
            st.session_state.messages = []
            st.rerun()


