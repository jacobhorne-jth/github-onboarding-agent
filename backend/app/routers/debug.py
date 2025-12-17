from fastapi import APIRouter, HTTPException
from pinecone import Pinecone
from ..config import settings

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/pinecone")
def pinecone_debug():
    if not settings.pinecone_api_key:
        raise HTTPException(500, "PINECONE_API_KEY is missing (not loaded from .env).")
    pc = Pinecone(api_key=settings.pinecone_api_key)
    idxs = pc.list_indexes()
    return {"indexes": idxs}
