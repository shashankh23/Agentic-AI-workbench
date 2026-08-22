import streamlit as st
from agent.agent import process_user_request
import os

st.title("Sovereign AI Workbench")
st.write("Secure, air-gapped agentic AI for industrial workflows.")

# Setup chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
if prompt := st.chat_input("Ask the AI to write code, analyze an image, or create a report..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call the agent (The Lead's code)
    with st.chat_message("assistant"):
        with st.spinner("Processing local AI task..."):
            # If we had an image upload, we'd pass it here. Keeping it simple for text first.
            response = process_user_request(prompt=prompt, image_path=None)
            st.markdown(response)
    
    st.session_state.messages.append({"role": "assistant", "content": response})