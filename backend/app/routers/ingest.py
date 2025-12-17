import os
from fastapi import APIRouter, HTTPException
from ..config import settings
from ..models.schemas import IngestRequest, IngestResponse
from ..services.github_loader import clone_or_update, iter_text_files, safe_repo_id
from ..services.chunker import make_chunks
from ..services.embeddings import HFEmbedder
from ..services.pinecone_store import PineconeStore

router = APIRouter(prefix="/ingest", tags=["ingest"])

@router.post("", response_model=IngestResponse)
def ingest(req: IngestRequest):
    if not settings.pinecone_api_key:
        raise HTTPException(500, "Missing PINECONE_API_KEY")

    repo_path, sha = clone_or_update(req.repo_url, settings.repos_dir, req.branch)
    repo_path_abs = os.path.abspath(repo_path)

    repo_id = safe_repo_id(req.repo_url)
    namespace = f"{repo_id}:{sha}"

    embedder = HFEmbedder(settings.hf_embed_model)
    store = PineconeStore(settings.pinecone_api_key, settings.pinecone_index)

    all_chunks = []
    for path, text in iter_text_files(repo_path_abs):
        all_chunks.extend(make_chunks(path, text))

    texts = [c.text for c in all_chunks]

    metas = []
    for c in all_chunks:
        md = dict(c.meta)

        # Normalize path for stable, clean citations + IDs
        p = md.get("path", "")
        if p:
            try:
                md["path"] = os.path.relpath(p, repo_path_abs).replace("\\", "/")
            except Exception:
                md["path"] = p.replace("\\", "/")

        # Store snippet for grounding (cap size to avoid bloated metadata)
        md["text"] = (c.text or "")[:2000]

        metas.append(md)

    vectors = embedder.embed_batch(texts)

    upserts = []
    for vec, meta in zip(vectors, metas):
        upserts.append({
            "id": f"{namespace}:{meta.get('path','unknown')}:{meta.get('chunk_index',0)}",
            "values": vec,
            "metadata": meta
        })

    # batch upsert
    B = 100
    for i in range(0, len(upserts), B):
        store.upsert(namespace, upserts[i:i+B])

    return IngestResponse(
        repo_id=repo_id,
        namespace=namespace,
        files_indexed=len(all_chunks),
    )
