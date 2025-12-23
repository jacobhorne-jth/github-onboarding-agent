from dataclasses import dataclass
from typing import Dict, List

@dataclass
class Chunk:
    text: str
    meta: Dict

def make_chunks(path: str, text: str, chunk_lines: int = 60, overlap: int = 10) -> List[Chunk]:
    """
    Split by lines with overlap so citations have real ranges.
    """
    lines = text.splitlines()
    out: List[Chunk] = []

    if not lines:
        return out

    step = max(1, chunk_lines - overlap)
    chunk_index = 0

    for start in range(0, len(lines), step):
        end = min(len(lines), start + chunk_lines)
        chunk_text = "\n".join(lines[start:end]).strip()
        if not chunk_text:
            continue

        out.append(Chunk(
            text=chunk_text,
            meta={
                "path": path,
                "chunk_index": chunk_index,
                "start_line": start + 1,
                "end_line": end,
            }
        ))
        chunk_index += 1

        if end >= len(lines):
            break

    return out
