"""The dispatch conversation held in the visitor's own browser, instead of over the phone.

The public dashboard has no telephony behind it: when an incident reaches the dispatch step, the
visitor's browser opens a WebRTC session straight to OpenAI's Realtime API and plays the part the
authority plays on the phone. Raqeeb reads the same Arabic briefing, from the same instructions,
and calls the same tool to record their decision. Only OpenAI minutes are spent.

This server never carries that audio. It mints a short-lived client secret for the session (the
API key must not reach a browser), and takes back the decision and the transcript when the
conversation ends.
"""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent.config import settings
from agent.graph.runner import get_incident_snapshot, resume_incident
from agent.providers.openai_llm import browser_audio_config, function_tools
from agent.voice.authority_prompts import RECORD_DISPATCH_CONFIRMATION_TOOL, build_dispatch_instructions

router = APIRouter(prefix="/api/incidents", tags=["browser-call"])

_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"

# A client secret is good for long enough to set the call up, not to hold one open: the
# conversation's own ceiling is settings.public_call_seconds, enforced by the browser.
_SECRET_SECONDS = 600

# One conversation per incident, so a visitor cannot reopen the same call over and over on our
# OpenAI account. Running a new detection is free to do and opens a new incident. Kept in memory:
# the deployment runs a single container, and a restart losing this only allows one extra
# conversation on an incident that survived it.
_started: set[str] = set()


class TranscriptLine(BaseModel):
    role: Literal["assistant", "authority"]
    text: str = Field(max_length=2000)


class BrowserCallResult(BaseModel):
    """What the browser saw. Anyone can post this, so nothing here is taken on trust beyond the
    incident it names: a confirmation is only recorded if the authority actually spoke, the same
    rule the phone path applies in agent/voice/sip_authority_call.py."""

    outcome: Literal["answered", "failed"] = "answered"
    dispatch_confirmed: bool = False
    authority_statement: str = Field(default="", max_length=2000)
    transcript: list[TranscriptLine] = Field(default_factory=list, max_length=200)


async def _awaiting_browser_call(incident_id: str):
    snapshot = await get_incident_snapshot(incident_id)
    if snapshot.next != ("gemini_authority_conversation",) or snapshot.values.get("call_transport") != "browser":
        raise HTTPException(status_code=409, detail="This incident is not waiting for a browser conversation.")
    return snapshot


@router.post("/{incident_id}/browser-call/token")
async def browser_call_token(incident_id: str):
    """A client secret for this incident's dispatch conversation, carrying its instructions.

    The session is fixed here rather than by the browser: the model, the voice, the briefing and
    the single tool it may call all come from the incident, so the secret cannot be repurposed
    into a general-purpose assistant on our account."""
    snapshot = await _awaiting_browser_call(incident_id)
    if incident_id in _started:
        raise HTTPException(status_code=409, detail="The conversation for this incident has already been held.")

    values = snapshot.values
    session = {
        "type": "realtime",
        "model": settings.openai_realtime_model,
        "instructions": build_dispatch_instructions(incident_id, values.get("report", {}), values.get("authority", {})),
        "audio": browser_audio_config(),
        "tools": function_tools([RECORD_DISPATCH_CONFIRMATION_TOOL]),
        "tool_choice": "auto",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            _CLIENT_SECRETS_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json={"session": session, "expires_after": {"anchor": "created_at", "seconds": _SECRET_SECONDS}},
        )
    if response.status_code >= 400:
        print(f"[browser-call {incident_id}] client secret refused: {response.status_code} {response.text[:300]}")
        raise HTTPException(status_code=502, detail="The conversation could not be started.")

    _started.add(incident_id)
    body = response.json()
    return {
        "client_secret": body["value"],
        "expires_at": body.get("expires_at"),
        "max_seconds": settings.public_call_seconds,
    }


@router.post("/{incident_id}/browser-call/result")
async def browser_call_result(incident_id: str, result: BrowserCallResult):
    """The end of the conversation: the authority's decision, or that it never happened."""
    await _awaiting_browser_call(incident_id)
    transcript = [line.model_dump() for line in result.transcript if line.text.strip()]
    heard_authority = any(line["role"] == "authority" for line in transcript)
    confirmed = bool(result.dispatch_confirmed and result.outcome == "answered" and heard_authority)

    await resume_incident(
        incident_id,
        {
            "dispatch_confirmed": confirmed,
            # "failed" holds the incident as one that reached no one, the same as a call that
            # never connected, so the dashboard explains itself the same way.
            "outcome": "answered" if result.outcome == "answered" else "failed",
            "authority_statement": result.authority_statement if confirmed else "",
            "raw_transcript": transcript,
        },
    )
    return {"incident_id": incident_id, "dispatch_confirmed": confirmed}
