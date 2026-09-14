"""Deploys the FastAPI backend to Modal.

    modal deploy modal_app.py

Why this shape:

- The whole ASGI app is served by one function rather than split into endpoints, because
  the graph, the Media Stream WebSocket and the monitor feed all have to live in the same
  process to see each other.
- A Volume holds the graph checkpoints, the SQLite incident database and uploads. Without
  it, an incident paused at employee verification is lost the moment the container
  recycles, which on a scale-to-zero platform is a matter of minutes.
- Secrets come from a Modal Secret, never from a committed .env.

The frontend is not served here. It deploys separately to Vercel and reaches this over
CORS, so a redeploy of one never disturbs the other.
"""

from __future__ import annotations

import modal

APP_NAME = "raqeeb"
VOLUME_PATH = "/data"

image = (
    modal.Image.debian_slim(python_version="3.12")
    # opencv needs these at import time; the slim image has neither
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "fastapi[standard]",
        "uvicorn[standard]",
        "python-multipart",
        "sqlalchemy",
        "httpx",
        "websockets",
        "pydantic-settings",
        "python-dotenv",
        "pyyaml",
        "langgraph",
        "langgraph-checkpoint-sqlite",
        "google-genai",
        "twilio",
        "ultralytics",
        "opencv-python-headless",
        "numpy",
    )
    # weights first and separately: they change far less often than the source, so this
    # layer stays cached across ordinary deploys
    .add_local_file("best_yolov8s.pt", "/app/best_yolov8s.pt", copy=True)
    .add_local_dir("config", "/app/config", copy=True)
    .add_local_python_source("agent")
)

app = modal.App(APP_NAME, image=image)

volume = modal.Volume.from_name(f"{APP_NAME}-state", create_if_missing=True)

# Created once with:
#   modal secret create raqeeb-secrets GEMINI_API_KEY=... TWILIO_ACCOUNT_SID=... ...
secrets = modal.Secret.from_name("raqeeb-secrets")


@app.function(
    volumes={VOLUME_PATH: volume},
    secrets=[secrets],
    # Live calls hold a WebSocket open for the length of the conversation.
    timeout=60 * 60,
    # One replica: the monitor fan-out in agent/monitor.py is per-process, so a second
    # container would serve a dashboard that never sees the call it is watching. Lift
    # this only after that moves to a shared broker.
    max_containers=1,
    # Cold start reloads torch and the model. Set this to 1 before a demo so an inbound
    # Twilio webhook is never the request that pays for it.
    min_containers=0,
    # The OpenAI call webhook returns as soon as the call is accepted, but the call itself
    # runs on in a background task for up to three minutes (_MAX_CALL_SECONDS plus the hangup
    # safety net in agent/voice/sip_authority_call.py). Modal's default 60 second idle window
    # could stop the container mid-call and lose the authority's decision.
    scaledown_window=5 * 60,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    import os

    # Point every piece of durable state at the Volume before the app imports settings.
    os.environ.setdefault("CHECKPOINT_DB", f"{VOLUME_PATH}/checkpoints.db")
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{VOLUME_PATH}/raqeeb.db")
    os.environ.setdefault("UPLOAD_DIR", f"{VOLUME_PATH}/uploads")
    os.environ.setdefault("YOLO_WEIGHTS_PATH", "/app/best_yolov8s.pt")
    os.environ.setdefault("AUTHORITY_MAPPING_PATH", "/app/config/authority_mapping.yaml")

    from fastapi.middleware.cors import CORSMiddleware

    from agent.main import app as fastapi

    # The dashboard is on a different origin once it is on Vercel.
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    fastapi.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        # A browser rejects a wildcard Access-Control-Allow-Origin on any credentialed
        # request, so the two can only be promised together once ALLOWED_ORIGINS names the
        # dashboard's origin explicitly. Nothing sends credentials today; this keeps the
        # fallback honest rather than quietly broken the first time something does.
        allow_credentials=bool(origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return fastapi
