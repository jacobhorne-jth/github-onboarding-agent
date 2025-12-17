from fastapi import FastAPI
from .routers import ingest, chat
from .routers import debug  # <-- add this

app = FastAPI()

app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(debug.router)  # <-- add this

@app.get("/health")
def health():
    return {"ok": True}
