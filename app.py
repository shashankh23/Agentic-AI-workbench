import streamlit as st
from agent.agent import process_user_request
from memory.memory import init_db, save_message, load_messages, clear_session
from network.network_monitor import get_network_snapshot
import os
import uuid

# ---- Page config ----
st.set_page_config(page_title="Sovereign AI Workbench", layout="wide")

# ---- Custom CSS ----
st.markdown("""
<style>
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #58a6ff;
        margin-bottom: 0;
    }
    .subtitle {
        color: #8b949e;
        font-size: 1rem;
        margin-top: 0;
    }
    .network-panel {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .status-clear {
        color: #3fb950;
        font-weight: 600;
    }
    .status-alert {
        color: #f85149;
        font-weight: 600;
    }
    div[data-testid="stChatMessage"] {
        background-color: #161b22;
        border-radius: 10px;
        padding: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ---- Init ----
init_db()
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = load_messages(st.session_state.session_id)

# ---- Header ----
st.markdown('<p class="main-title">🛡️ Sovereign AI Workbench</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Secure, air-gapped agentic AI for industrial workflows — zero external calls.</p>', unsafe_allow_html=True)

# ---- Sidebar: Network Audit Panel ----
with st.sidebar:
    st.markdown("### 🔒 Network Audit")
    snapshot = get_network_snapshot()
    
    if snapshot["external_count"] == 0:
        st.markdown('<p class="status-clear">✅ No external connections detected</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="status-alert">⚠️ {snapshot["external_count"]} external connection(s) detected</p>', unsafe_allow_html=True)
        for conn in snapshot["external_connections"]:
            st.text(conn)
    
    st.metric("Bytes Sent (system-wide)", f"{snapshot['bytes_sent'] / 1024:.1f} KB")
    st.metric("Bytes Received (system-wide)", f"{snapshot['bytes_recv'] / 1024:.1f} KB")
    
    if st.button("🔄 Refresh Network Status"):
        st.rerun()
    
    st.markdown("---")
    if st.button("🗑️ Clear Session History"):
        clear_session(st.session_state.session_id)
        st.session_state.messages = []
        st.rerun()

# ---- Chat history ----
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ---- File uploader ----
uploaded_file = st.file_uploader("Upload an image or report (optional)", type=["png", "jpg", "jpeg", "pdf", "txt"])
saved_path = None
if uploaded_file is not None:
    saved_path = os.path.join("uploads", uploaded_file.name)
    os.makedirs("uploads", exist_ok=True)
    with open(saved_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success(f"Uploaded: {uploaded_file.name}")

# ---- Chat input ----
if prompt := st.chat_input("Ask the AI to write code, analyze an image, or create a report..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(st.session_state.session_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Processing local AI task..."):
            response = process_user_request(prompt=prompt, image_path=saved_path, history=st.session_state.messages)
            st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
    save_message(st.session_state.session_id, "assistant", response)