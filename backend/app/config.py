from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_index: str = os.getenv("PINECONE_INDEX", "github-onboarding")
    pinecone_env: str = os.getenv("PINECONE_ENV", "us-east-1")
    hf_embed_model: str = os.getenv("HF_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    repos_dir: str = os.getenv("REPOS_DIR", ".repos")

settings = Settings()
