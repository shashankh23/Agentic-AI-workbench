import streamlit as st
from agent.agent import process_user_request
import os

st.title("Sovereign AI Workbench")
st.write("Secure, air-gapped agentic AI for industrial workflows.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# File uploader for images/reports
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
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Processing local AI task..."):
            response = process_user_request(prompt=prompt, image_path=saved_path)
            st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})