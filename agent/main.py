from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.config import settings
from agent.db import init_db
from agent.routes import detection, openai_routes, twilio_routes, verification, voice_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.llm_provider.lower() == "openai" and not settings.openai_webhook_secret:
        raise RuntimeError(
            "LLM_PROVIDER=openai requires OPENAI_WEBHOOK_SECRET -- the SIP callback in "
            "agent/routes/openai_routes.py cannot authenticate OpenAI without it."
        )
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Raqeeb Voice Agent", lifespan=lifespan)

app.include_router(detection.router)
app.include_router(verification.router)
app.include_router(voice_ws.router)
app.include_router(twilio_routes.router)
app.include_router(openai_routes.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir, check_dir=False), name="uploads")
