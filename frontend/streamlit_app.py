import streamlit as st
import requests

BACKEND = "http://127.0.0.1:8000"

st.set_page_config(page_title="GitHub Onboarding Agent", layout="wide")
st.title("GitHub Onboarding Agent")

# -----------------------
# Session state
# -----------------------
if "namespace" not in st.session_state:
    st.session_state.namespace = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "ingesting" not in st.session_state:
    st.session_state.ingesting = False
if "namespaces" not in st.session_state:
    # simple history of namespaces you've ingested this session
    st.session_state.namespaces = []


def set_namespace(new_ns: str):
    """Set active namespace; clear chat if changing repos."""
    old_ns = st.session_state.namespace
    if old_ns and old_ns != new_ns:
        st.session_state.messages = []  # prevent cross-repo mixing
    st.session_state.namespace = new_ns

    # track history
    if new_ns and new_ns not in st.session_state.namespaces:
        st.session_state.namespaces.insert(0, new_ns)


# -----------------------
# Sidebar: Ingest + controls
# -----------------------
with st.sidebar:
    st.header("Index a Repo")
    repo_url = st.text_input("GitHub repo URL", placeholder="https://github.com/user/repo")

    col1, col2 = st.columns(2)
    ingest_clicked = col1.button("Ingest", disabled=st.session_state.ingesting)
    clear_clicked = col2.button("Clear chat")

    if clear_clicked:
        st.session_state.messages = []
        st.toast("Chat cleared.", icon="🧹")

    if ingest_clicked:
        if not repo_url or not repo_url.strip():
            st.error("Please paste a GitHub repo URL first.")
        else:
            st.session_state.ingesting = True
            try:
                with st.spinner("Ingesting repo (clone → chunk → embed → upsert)…"):
                    r = requests.post(
                        f"{BACKEND}/ingest",
                        json={"repo_url": repo_url.strip()},
                        timeout=600,
                    )

                if r.ok:
                    data = r.json()
                    new_ns = data["namespace"]
                    set_namespace(new_ns)

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

    # Optional: switch between previously ingested namespaces
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
            st.toast(f"Switched to {choice}", icon="🔁")

    st.divider()
    st.caption("Backend: " + BACKEND)
    st.caption("Current namespace: " + (st.session_state.namespace or "None"))

# -----------------------
# Main: Chat
# -----------------------
st.subheader("Chatbot")
st.caption(f"Active namespace: {st.session_state.namespace or 'None'}")

if not st.session_state.namespace:
    st.info("Ingest a repo first (left sidebar).")
    st.stop()

# Render chat history
for role, content in st.session_state.messages:
    with st.chat_message(role):
        st.write(content)

prompt = st.chat_input("Ask about the repo…")
if prompt:
    st.session_state.messages.append(("user", prompt))
    with st.chat_message("user"):
        st.write(prompt)

    try:
        with st.spinner("Thinking…"):
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
            st.session_state.messages.append(("assistant", ans))
            with st.chat_message("assistant"):
                st.write(ans)
        else:
            st.error(r.text)
    except requests.RequestException as e:
        st.error(f"Chat request failed: {e}")
