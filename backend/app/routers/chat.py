from fastapi import APIRouter, HTTPException
from ..config import settings
from ..models.schemas import ChatRequest, ChatResponse, Source
from ..services.embeddings import HFEmbedder
from ..services.pinecone_store import PineconeStore
from ..services.graph import build_graph

router = APIRouter(prefix="/chat", tags=["chat"])


def make_prompt(question: str, hits: list[dict]) -> str:
    # Use more context for onboarding
    blocks = []
    for i, h in enumerate(hits[:14], start=1):
        md = h.get("metadata") or {}
        path = md.get("path", "(unknown)")
        start = md.get("start_line", 1)
        end = md.get("end_line", 1)
        text = (md.get("text") or "").strip()

        # cap each chunk to keep prompt manageable
        text = text[:1400]

        blocks.append(f"[S{i}] {path} (lines {start}-{end})\n{text}")

    context = "\n\n".join(blocks) if blocks else "(no relevant context found)"

    return f"""You are a GitHub repo onboarding assistant.

Goal: Answer the user question using the repository contents, even if there is no README.

Use ONLY the sources below. Do not ask the user to read the README; if README content is present in sources, summarize it.

User question: {question}

Sources:
{context}

Output format (use these headings):
1) What this repo is
2) What it likely does (inferred from code/config if no explicit description)
3) How to run it locally (only if present in sources)
4) Development workflow (tests/lint/format/CI if present)
5) Key directories / entry points (prioritize src/ and package code, not tooling folders)
6) Suggested first tasks for a new contributor (3 bullets)

Rules:
- If you infer something, say “Likely:” and cite the source(s) that support the inference.
- Cite sources like [S1], [S2] at the end of each statement/bullet.
- Prefer core code paths (src/, package modules) over tooling (devcontainer, CI) unless asked.
"""


def _score_boost(h: dict) -> float:
    md = h.get("metadata") or {}
    path = (md.get("path") or "").lower()

    s = float(h.get("score", 0.0))

    # Prefer core code
    if path.startswith("src/"):
        s += 0.20
    if "/__init__.py" in path or path.endswith("__init__.py"):
        s += 0.10
    if path.startswith("flask/") or path.startswith("app/") or path.startswith("backend/"):
        s += 0.05

    # Prefer docs/readme when present
    if md.get("is_readme") or path.endswith("readme.md") or path.endswith("readme.rst"):
        s += 0.25
    if md.get("is_doc") or path.startswith("docs/") or path.startswith("doc/"):
        s += 0.12

    # Helpful metadata files
    if path in {"pyproject.toml", "setup.cfg", "setup.py"}:
        s += 0.10

    # De-prioritize noise unless explicitly asked
    noisy_prefixes = (".devcontainer/", ".github/", ".circleci/", ".gitlab/", "devcontainer/")
    noisy_contains = ("tests/", ".repos/")
    if path.startswith(noisy_prefixes):
        s -= 0.10
    if path.startswith(noisy_contains):
        s -= 0.05

    return s


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not settings.pinecone_api_key:
        raise HTTPException(500, "Missing PINECONE_API_KEY")

    embedder = HFEmbedder(settings.hf_embed_model)
    store = PineconeStore(settings.pinecone_api_key, settings.pinecone_index)

    def retriever_fn(namespace: str, question: str):
        # Multi-query retrieval for onboarding
        queries = [
            question,
            f"{question}\nFind the purpose/overview/description of the project.",
            f"{question}\nFind how to run/install/setup this project.",
            f"{question}\nFind how to test/lint/format and dev workflow.",
            # Code-focused queries so we can infer purpose even without README
            "Project purpose module docstring overview package description __init__",
            "Entry points main app create_app cli console_scripts",
            "src/ package architecture key modules",
        ]

        candidates: list[dict] = []

        for q in queries:
            qvec = embedder.embed_batch([q])[0]
            res = store.query(namespace, qvec, top_k=18)
            matches = res.get("matches", []) if isinstance(res, dict) else res.matches

            for m in matches:
                md = m["metadata"] if isinstance(m, dict) else m.metadata
                score = m["score"] if isinstance(m, dict) else m.score
                candidates.append({"score": float(score), "metadata": md})

        # De-dup by (path, chunk_index)
        seen = set()
        deduped = []
        for h in candidates:
            md = h.get("metadata") or {}
            k = (md.get("path"), md.get("chunk_index"))
            if k in seen:
                continue
            seen.add(k)
            deduped.append(h)

        # Boost / rerank
        deduped.sort(key=_score_boost, reverse=True)
        return deduped[:18]

    def answer_fn(question: str, hits: list[dict]) -> str:
        if not hits:
            return "I couldn’t find anything relevant in the indexed repo. Try asking with a filename, module name, or keyword."

        # If no LLM key, still provide useful summary based on paths
        if not settings.openai_api_key:
            top = hits[:8]
            lines = "\n".join([f"- {h['metadata'].get('path','(unknown)')}" for h in top])
            return (
                "I can retrieve the most relevant files, but full synthesis requires an LLM key.\n\n"
                f"Top relevant files:\n{lines}\n\n"
                "Set OPENAI_API_KEY to enable a full onboarding answer."
            )

        # Use your existing OpenAI LLM wrapper if present
        from ..services.openai_llm import OpenAILLM

        llm = OpenAILLM(settings.openai_api_key, settings.openai_model)
        prompt = make_prompt(question, hits)
        return llm.generate(prompt)

    graph = build_graph(retriever_fn=retriever_fn, answer_fn=answer_fn)
    state = graph.invoke({"namespace": req.namespace, "question": req.message})

    sources = []
    for h in (state.get("hits") or [])[:10]:
        md = h.get("metadata") or {}
        sources.append(Source(
            path=md.get("path", ""),
            start_line=int(md.get("start_line", 1)),
            end_line=int(md.get("end_line", 1)),
            snippet=(md.get("text", "") or "")[:800],
        ))

    return ChatResponse(answer=state["answer"], sources=sources)
