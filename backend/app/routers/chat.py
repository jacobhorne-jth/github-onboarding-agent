from fastapi import APIRouter, HTTPException
from ..config import settings
from ..models.schemas import ChatRequest, ChatResponse, Source
from ..services.embeddings import HFEmbedder
from ..services.pinecone_store import PineconeStore
from ..services.graph import build_graph
from ..services.openai_llm import OpenAILLM

router = APIRouter(prefix="/chat", tags=["chat"])


def make_prompt(question: str, hits: list[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits[:6], start=1):
        md = h.get("metadata") or {}
        path = md.get("path", "(unknown)")
        start = md.get("start_line", 1)
        end = md.get("end_line", 1)
        text = (md.get("text") or "").strip()

        # Keep prompts from blowing up
        text = text[:1500]

        blocks.append(f"[S{i}] {path} (lines {start}-{end})\n{text}")

    context = "\n\n".join(blocks) if blocks else "(no relevant context found)"

    return f"""You are a GitHub repo onboarding assistant.

Task: Give an onboarding summary that helps a new contributor succeed.

Use ONLY the sources below. If something is unknown, say "Not found in sources."

User question: {question}

Sources:
{context}

Output format (exact headings):
1) What this repo is (1–2 sentences)
2) How to run it locally (commands, if present)
3) Development workflow (lint/format/test, pre-commit, CI)
4) Key directories / entry points (name the folders/files)
5) Suggested first tasks for a new contributor (3 bullets)

Citations:
- Put citations like [S1] at the end of each bullet/sentence that uses a source.
- Do not cite sources you didn't use.
"""


def _boost_score(md: dict) -> int:
    p = (md.get("path") or "").lower()

    # strongest: README + docs + contributing
    if p.endswith("readme.md") or p == "readme.md":
        return 120
    if "contributing" in p or "quickstart" in p or "getting_started" in p:
        return 110
    if p.startswith("docs/") or "/docs/" in p:
        return 95

    # library source code (Flask repo uses src/flask)
    if p.startswith("src/flask/") or "/src/flask/" in p:
        return 90

    # tests should be later for "what is this repo"
    if p.startswith("tests/") or "/tests/" in p:
        return 20

    # configs / build
    if p.endswith("pyproject.toml") or p.endswith("setup.py") or p.endswith("requirements.txt"):
        return 60

    # tooling last
    if ".github/workflows" in p:
        return 10
    if "pre-commit" in p:
        return 5

    # general code
    if p.endswith(".py") or p.endswith(".ts") or p.endswith(".js"):
        return 40

    return 0



def _dedupe_hits(hits: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for h in hits:
        md = h.get("metadata") or {}
        key = (
            md.get("path", ""),
            md.get("start_line", ""),
            md.get("end_line", ""),
            md.get("chunk_index", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def answer_with_llm(question: str, hits: list[dict]) -> str:
    if not hits:
        return "I couldn’t find anything relevant in the indexed repo. Try asking with a filename, function name, or keyword."

    if not settings.openai_api_key:
        top = hits[:6]
        bullets = "\n".join([f"- {h['metadata'].get('path','(unknown)')}" for h in top])
        return (
            f"Top relevant files for: **{question}**\n\n{bullets}\n\n"
            "Set OPENAI_API_KEY in your .env to enable full answers."
        )

    llm = OpenAILLM(settings.openai_api_key, settings.openai_model)
    prompt = make_prompt(question, hits)
    return llm.generate(prompt)


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not settings.pinecone_api_key:
        raise HTTPException(500, "Missing PINECONE_API_KEY")

    embedder = HFEmbedder(settings.hf_embed_model)
    store = PineconeStore(settings.pinecone_api_key, settings.pinecone_index)

    def retriever_fn(namespace: str, question: str):
        # Multi-query retrieval for generic onboarding questions
        queries = [question.strip()]
        if len(queries[0].split()) <= 8:
            queries += [
                "README overview purpose installation usage",
                "src/flask app.py __init__.py what is this library",
                "how to run tests pytest tox nox",
                "contributing development workflow pre-commit",
            ]

        all_hits = []

        for q in queries:
            qvec = embedder.embed_batch([q])[0]
            res = store.query(namespace, qvec, top_k=10)

            matches = res.get("matches", []) if isinstance(res, dict) else res.matches
            for m in matches:
                md = m["metadata"] if isinstance(m, dict) else m.metadata
                score = m["score"] if isinstance(m, dict) else m.score
                all_hits.append({"score": score, "metadata": md})

        # Dedupe then boost-sort
        all_hits = _dedupe_hits(all_hits)

        all_hits.sort(
            key=lambda h: (_boost_score(h.get("metadata") or {}), h.get("score", 0.0)),
            reverse=True,
        )

        # Keep a reasonable number for prompt building
        return all_hits[:12]

    graph = build_graph(retriever_fn=retriever_fn, answer_fn=answer_with_llm)
    state = graph.invoke({"namespace": req.namespace, "question": req.message})

    sources = []
    for h in (state.get("hits") or [])[:6]:
        md = h.get("metadata") or {}
        sources.append(
            Source(
                path=md.get("path", ""),
                start_line=int(md.get("start_line", 1)),
                end_line=int(md.get("end_line", 1)),
                snippet=(md.get("text", "") or "")[:800],
            )
        )

    return ChatResponse(answer=state["answer"], sources=sources)
