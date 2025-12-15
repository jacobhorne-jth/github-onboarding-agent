import streamlit as st
import requests

BACKEND = "http://localhost:8000"

st.set_page_config(page_title="GitHub Onboarding Agent", layout="wide")
st.title("GitHub Onboarding Agent")

if "namespace" not in st.session_state:
    st.session_state.namespace = None
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Index a Repo")
    repo_url = st.text_input("GitHub repo URL", placeholder="https://github.com/user/repo")
    if st.button("Ingest"):
        r = requests.post(f"{BACKEND}/ingest", json={"repo_url": repo_url})
        if r.ok:
            data = r.json()
            st.session_state.namespace = data["namespace"]
            st.success(f"Indexed! namespace = {st.session_state.namespace}")
        else:
            st.error(r.text)

st.subheader("Chatbot")

if not st.session_state.namespace:
    st.info("Ingest a repo first.")
    st.stop()

for role, content in st.session_state.messages:
    with st.chat_message(role):
        st.write(content)

prompt = st.chat_input("Ask about the repo…")
if prompt:
    st.session_state.messages.append(("user", prompt))
    with st.chat_message("user"):
        st.write(prompt)

    r = requests.post(f"{BACKEND}/chat", json={
        "namespace": st.session_state.namespace,
        "message": prompt,
        "session_id": "default"
    })
    if r.ok:
        ans = r.json()["answer"]
        st.session_state.messages.append(("assistant", ans))
        with st.chat_message("assistant"):
            st.write(ans)
    else:
        st.error(r.text)
