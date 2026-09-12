from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.config import settings, validate_settings
from agent.db import init_db
from agent.routes import detection, monitor_ws, openai_routes, twilio_routes, verification, voice_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Raqeeb Voice Agent", lifespan=lifespan)

app.include_router(detection.router)
app.include_router(verification.router)
app.include_router(voice_ws.router)
app.include_router(twilio_routes.router)
app.include_router(openai_routes.router)
app.include_router(monitor_ws.router)

BASE_DIR = Path(__file__).resolve().parent.parent
# The dashboard is a built Vite bundle. It also deploys standalone to Vercel, so serving
# it here is a convenience for local runs, not the only path to it.
DASHBOARD_DIR = BASE_DIR / "frontend" / "dist"
if DASHBOARD_DIR.is_dir():
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir, check_dir=False), name="uploads")
