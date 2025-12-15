from dataclasses import dataclass
from typing import List, Dict
import os

@dataclass
class Chunk:
    text: str
    meta: Dict

def chunk_text(text: str, max_chars: int = 3500, overlap: int = 400) -> List[str]:
    # simple deterministic chunker (upgrade to structure-aware later)
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        chunks.append(text[i:j])
        i = max(0, j - overlap)
        if j == len(text):
            break
    return chunks

def make_chunks(path: str, text: str) -> List[Chunk]:
    rel = path.replace("\\", "/")
    parts = chunk_text(text)
    out = []
    for idx, p in enumerate(parts):
        out.append(Chunk(
            text=p,
            meta={
                "path": rel,
                "chunk_index": idx,
                "start_line": 1,   # placeholders (line mapping later)
                "end_line": 1
            }
        ))
    return out
