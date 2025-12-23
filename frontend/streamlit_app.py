import streamlit as st
import requests
import os

BACKEND = st.secrets.get("BACKEND_URL", os.getenv("BACKEND_URL", "http://127.0.0.1:8000"))

st.set_page_config(page_title="GitHub Onboarding Agent", layout="wide")
st.title("GitHub Onboarding Agent")

if "namespace" not in st.session_state:
    st.session_state.namespace = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "ingesting" not in st.session_state:
    st.session_state.ingesting = False
if "namespaces" not in st.session_state:
    st.session_state.namespaces = []

def set_namespace(new_ns: str):
    old = st.session_state.namespace
    if old and old != new_ns:
        st.session_state.messages = []
    st.session_state.namespace = new_ns
    if new_ns and new_ns not in st.session_state.namespaces:
        st.session_state.namespaces.insert(0, new_ns)

with st.sidebar:
    st.header("Index a Repo")
    repo_url = st.text_input("GitHub repo URL", placeholder="https://github.com/user/repo")

    col1, col2 = st.columns(2)
    ingest_clicked = col1.button("Ingest", disabled=st.session_state.ingesting)
    clear_clicked = col2.button("Clear chat")

    if clear_clicked:
        st.session_state.messages = []
        st.toast("Chat cleared.", icon="✅")

    if ingest_clicked:
        if not repo_url or not repo_url.strip():
            st.error("Paste a GitHub repo root URL first.")
        else:
            st.session_state.ingesting = True
            try:
                with st.spinner("Ingesting (clone → chunk → embed → upsert)…"):
                    r = requests.post(
                        f"{BACKEND}/ingest",
                        json={"repo_url": repo_url.strip()},
                        timeout=900,
                    )
                if r.ok:
                    data = r.json()


                    st.session_state.namespace = data["namespace"]
                    st.session_state.messages = []  # reset chat when switching repos

                    files_indexed = data.get("files_indexed")
                    if files_indexed is not None:
                        st.success(f"Indexed! {files_indexed} chunks → namespace = {st.session_state.namespace}")
                    else:
                        st.success(f"Indexed! namespace = {st.session_state.namespace}")
                else:
                    st.error(r.text)
            except requests.RequestException as e:
                st.error(f"Request failed: {e}")
            finally:
                st.session_state.ingesting = False

    if st.session_state.namespaces:
        st.divider()
        st.subheader("Switch repo")
        choice = st.selectbox(
            "Active namespace",
            options=st.session_state.namespaces,
            index=st.session_state.namespaces.index(st.session_state.namespace)
            if st.session_state.namespace in st.session_state.namespaces
            else 0,
        )
        if choice and choice != st.session_state.namespace:
            set_namespace(choice)
            st.toast("Switched repository.", icon="✅")

    st.divider()
    st.caption(f"Backend: {BACKEND}")
    st.caption(f"Active namespace: {st.session_state.namespace or 'None'}")

st.subheader("Chatbot")
st.caption(f"Active namespace: {st.session_state.namespace or 'None'}")

if not st.session_state.namespace:
    st.info("Ingest a repo first (left sidebar).")
    st.stop()

# Render history (store dicts so we can show sources)
for msg in st.session_state.messages:
    role = msg["role"]
    content = msg["content"]
    with st.chat_message(role):
        st.write(content)
        if role == "assistant" and msg.get("sources"):
            with st.expander("Sources"):
                for s in msg["sources"]:
                    st.write(f"{s['path']} (lines {s['start_line']}-{s['end_line']})")
                    if s.get("snippet"):
                        st.code(s["snippet"])

prompt = st.chat_input("Ask about the repo…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    try:
        with st.spinner("Retrieving…"):
            r = requests.post(
                f"{BACKEND}/chat",
                json={
                    "namespace": st.session_state.namespace,
                    "message": prompt,
                    "session_id": "default",
                },
                timeout=180,
            )

        if r.ok:
            payload = r.json()
            ans = payload.get("answer", "")
            sources = payload.get("sources", [])
            st.session_state.messages.append({"role": "assistant", "content": ans, "sources": sources})

            with st.chat_message("assistant"):
                st.write(ans)
                if sources:
                    with st.expander("Sources"):
                        for s in sources:
                            st.write(f"{s['path']} (lines {s['start_line']}-{s['end_line']})")
                            if s.get("snippet"):
                                st.code(s["snippet"])
        else:
            st.error(r.text)
    except requests.RequestException as e:
        st.error(f"Chat request failed: {e}")
