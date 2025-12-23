import os
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models.schemas import IngestRequest, IngestResponse
from ..services.github_loader import (
    clone_or_update,
    iter_text_files,
    safe_repo_id,
    normalize_github_repo_url,
)
from ..services.chunker import make_chunks
from ..services.embeddings import HFEmbedder
from ..services.pinecone_store import PineconeStore

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _build_metadata(repo_path: str, c) -> dict:
    """
    Standardize metadata to be:
      - repo-relative path (forward slashes)
      - doc/readme flags
      - include snippet text (capped) for grounding
    """
    md = dict(c.meta)

    # c.meta["path"] might be absolute or relative depending on iter_text_files()
    raw_path = (md.get("path") or "").replace("\\", "/")

    # Make repo-relative for stability and nicer display
    # If already relative, this won't break.
    try:
        rel = os.path.relpath(raw_path, repo_path).replace("\\", "/")
        # If rel starts with "..", raw_path was already relative; keep raw_path
        if rel.startswith(".."):
            rel = raw_path
    except Exception:
        rel = raw_path

    rel = rel.lstrip("./")

    filename = os.path.basename(rel).lower()
    ext = os.path.splitext(filename)[1].lower()

    is_readme = filename in {"readme.md", "readme.rst", "readme.txt"}
    is_doc = is_readme or rel.startswith("docs/") or rel.startswith("doc/")

    md["path"] = rel
    md["filename"] = filename
    md["ext"] = ext
    md["is_readme"] = is_readme
    md["is_doc"] = is_doc

    # Store snippet text for grounding (cap to avoid huge metadata)
    md["text"] = (c.text or "")[:1200]

    return md


@router.post("", response_model=IngestResponse)
def ingest(req: IngestRequest):
    if not settings.pinecone_api_key:
        raise HTTPException(500, "Missing PINECONE_API_KEY")

    # Normalize GitHub URL (strip /tree/... etc to repo root)
    try:
        normalized = normalize_github_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Clone or update repo
    try:
        repo_path, sha = clone_or_update(normalized, settings.repos_dir, req.branch)
    except Exception as e:
        raise HTTPException(500, f"Failed to clone/update repo: {e}")

    repo_id = safe_repo_id(normalized)
    namespace = f"{repo_id}:{sha}"

    embedder = HFEmbedder(settings.hf_embed_model)
    store = PineconeStore(settings.pinecone_api_key, settings.pinecone_index)

    # Load + chunk repo files
    all_chunks = []
    for rel_path, text in iter_text_files(repo_path):
        all_chunks.extend(make_chunks(rel_path, text))

    if not all_chunks:
        raise HTTPException(400, "No indexable text/code files found.")

    # Embed
    texts = [c.text for c in all_chunks]
    vectors = embedder.embed_batch(texts)

    # Prepare upserts
    upserts = []
    for vec, c in zip(vectors, all_chunks):
        md = _build_metadata(repo_path, c)
        upserts.append(
            {
                "id": f"{namespace}:{md['path']}:{md['chunk_index']}",
                "values": vec,
                "metadata": md,
            }
        )

    # Upsert in batches
    B = 100
    for i in range(0, len(upserts), B):
        store.upsert(namespace, upserts[i : i + B])

    # Return (assumes IngestResponse has repo_url; see note below)
    return IngestResponse(
        repo_id=repo_id,
        namespace=namespace,
        files_indexed=len(all_chunks),
        repo_url=normalized,
    )
