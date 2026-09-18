from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agent.config import settings, validate_settings
from agent.db import init_db
from agent.routes import admin, browser_call, detection, monitor_ws, openai_routes, twilio_routes, verification, voice_ws


class ReadableServerErrors:
    """Turns an unhandled exception into a JSON 500 from *inside* whatever middleware wraps
    this app -- CORS above all.

    Starlette's own ServerErrorMiddleware sits outside every middleware added with
    add_middleware, so the bare 500 it produces never passes back through CORSMiddleware and
    carries no Access-Control-Allow-Origin header. A browser discards a cross-origin response
    like that without reading it, so the dashboard (on Vercel, a different origin from the API)
    reports an opaque network failure -- "TypeError: Load failed" in Safari -- no matter what
    actually went wrong. Catching the exception here, under CORS, lets the reason reach it.

    The traceback is still printed, so the server log keeps everything it showed before.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def sender(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, sender)
        except Exception as exc:
            traceback.print_exc()
            if started:
                # the response is already on the wire, so there is nothing left to replace
                raise
            detail = f"{type(exc).__name__}: {exc}"
            await JSONResponse({"detail": detail}, status_code=500)(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Raqeeb Voice Agent", lifespan=lifespan)

# Added before any CORS middleware (modal_app.py adds that later, and a later add_middleware
# wraps an earlier one), which is the whole point: the error response has to travel back out
# through CORS to be readable by a dashboard on another origin.
app.add_middleware(ReadableServerErrors)

app.include_router(admin.router)
app.include_router(browser_call.router)
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
