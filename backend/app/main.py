from fastapi import FastAPI
from .routers import ingest, chat

app = FastAPI(title="GitHub Onboarding Agent")

app.include_router(ingest.router)
app.include_router(chat.router)

@app.get("/health")
def health():
    return {"ok": True}
