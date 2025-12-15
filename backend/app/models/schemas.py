from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class IngestRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None

class IngestResponse(BaseModel):
    repo_id: str
    namespace: str
    files_indexed: int

class ChatRequest(BaseModel):
    namespace: str
    message: str
    session_id: str = "default"

class Source(BaseModel):
    path: str
    start_line: int
    end_line: int
    snippet: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = Field(default_factory=list)
    debug: Optional[Dict] = None
