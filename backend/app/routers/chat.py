from fastapi import APIRouter, HTTPException
from ..config import settings
from ..models.schemas import ChatRequest, ChatResponse, Source
from ..services.embeddings import HFEmbedder
from ..services.pinecone_store import PineconeStore
from ..services.graph import build_graph

router = APIRouter(prefix="/chat", tags=["chat"])

def format_answer(question: str, hits):
    # MVP: simple grounded response (upgrade to an LLM in next step)
    if not hits:
        return "I couldn’t find anything relevant in the indexed repo. Try asking with a filename, function name, or keyword."
    top = hits[:4]
    bullets = "\n".join([f"- {h['metadata'].get('path','(unknown)')}" for h in top])
    return f"Here are the most relevant files/chunks I found for: **{question}**\n\n{bullets}\n\nAsk a more specific question and I’ll narrow it down."

@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not settings.pinecone_api_key:
        raise HTTPException(500, "Missing PINECONE_API_KEY")

    embedder = HFEmbedder(settings.hf_embed_model)
    store = PineconeStore(settings.pinecone_api_key, settings.pinecone_index)

    def retriever_fn(namespace: str, question: str):
        qvec = embedder.embed_batch([question])[0]
        res = store.query(namespace, qvec, top_k=8)
        matches = res.get("matches", []) if isinstance(res, dict) else res.matches
        hits = []
        for m in matches:
            md = m["metadata"] if isinstance(m, dict) else m.metadata
            hits.append({"score": m["score"] if isinstance(m, dict) else m.score, "metadata": md})
        return hits

    graph = build_graph(retriever_fn=retriever_fn, answer_fn=format_answer)
    state = graph.invoke({"namespace": req.namespace, "question": req.message})

    sources = []
    for h in (state.get("hits") or [])[:6]:
        md = h["metadata"]
        sources.append(Source(
            path=md.get("path",""),
            start_line=int(md.get("start_line", 1)),
            end_line=int(md.get("end_line", 1)),
            snippet=""  # we’ll add snippet text mapping later
        ))

    return ChatResponse(answer=state["answer"], sources=sources)
