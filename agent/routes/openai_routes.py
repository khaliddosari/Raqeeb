"""Receives OpenAI's realtime.call.incoming webhook -- fired when Twilio's SIP leg for
an authority call (see TwilioTelephonyProvider.build_stream_twiml) reaches
sip.api.openai.com. We match it back to our incident via the X-Incident-Id SIP header
we set when dialing, accept the call with that incident's instructions, and hand off
to agent/voice/sip_authority_call.py to drive the rest."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, HTTPException, Request, Response

from agent.config import settings
from agent.graph.runner import get_incident_snapshot
from agent.voice.sip_authority_call import accept_call, observe_and_drive

router = APIRouter(prefix="/api/openai", tags=["openai"])

_TIMESTAMP_TOLERANCE_SECONDS = 300


def _verify_signature(body: bytes, headers: dict[str, str]) -> None:
    """Standard Webhooks (https://www.standardwebhooks.com) HMAC verification, matching
    what the `openai` SDK's client.webhooks.unwrap() does -- reimplemented directly so
    we don't need that package (see agent/providers/openai_llm.py for why)."""
    signature_header = headers.get("webhook-signature")
    timestamp = headers.get("webhook-timestamp")
    webhook_id = headers.get("webhook-id")
    if not signature_header or not timestamp or not webhook_id:
        raise HTTPException(status_code=400, detail="Missing webhook signature headers")

    try:
        timestamp_seconds = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook timestamp") from None
    if abs(int(time.time()) - timestamp_seconds) > _TIMESTAMP_TOLERANCE_SECONDS:
        raise HTTPException(status_code=400, detail="Webhook timestamp outside tolerance")

    secret = settings.openai_webhook_secret
    if not secret:
        # Without this an unset secret would HMAC with an empty key, which any caller can
        # reproduce -- i.e. every forged webhook would verify.
        raise HTTPException(status_code=500, detail="Webhook secret is not configured")
    decoded_secret = base64.b64decode(secret[6:]) if secret.startswith("whsec_") else secret.encode()
    signed_payload = f"{webhook_id}.{timestamp}.{body.decode('utf-8')}"
    expected = base64.b64encode(hmac.new(decoded_secret, signed_payload.encode(), hashlib.sha256).digest()).decode()

    signatures = [part[3:] if part.startswith("v1,") else part for part in signature_header.split()]
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")


@router.post("/webhook")
async def openai_webhook(request: Request) -> Response:
    body = await request.body()
    _verify_signature(body, {k.lower(): v for k, v in request.headers.items()})

    event = json.loads(body)
    if event.get("type") != "realtime.call.incoming":
        return Response(status_code=200)

    call_id = event["data"]["call_id"]
    sip_headers = {h["name"].lower(): h["value"] for h in event["data"].get("sip_headers", [])}
    incident_id = sip_headers.get("x-incident-id")
    if not incident_id:
        # Not a call we placed (or the header got stripped somewhere) -- nothing to
        # accept it with, so leave it alone rather than accept blind.
        return Response(status_code=200)

    snapshot = await get_incident_snapshot(incident_id)
    report = snapshot.values.get("report", {})

    await accept_call(call_id, incident_id, report)
    asyncio.create_task(observe_and_drive(call_id, incident_id))
    return Response(status_code=200)
