from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect

from agent.config import settings
from agent.graph.runner import end_unanswered_call, get_incident_snapshot, resume_incident
from agent.providers.factory import get_telephony_provider
from agent.providers.twilio_telephony import status_callback_url, voice_webhook_url
from agent.voice.authority_call_session import AuthorityCallSession

router = APIRouter(tags=["twilio"])

# CallStatus values on the final status callback of a call that never connected to anyone.
_NEVER_CONNECTED = {"busy": "busy", "no-answer": "no_answer", "failed": "failed", "canceled": "failed"}

_HANGUP_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


async def _signed_form(request: Request, url: str) -> dict[str, str]:
    """The webhook's form fields, once X-Twilio-Signature proves Twilio sent them.

    These webhooks change an incident (a voicemail or a missed call ends the dispatch call), and the
    call SID they name is visible on the incident API, so a forged request must not pass. The URL is
    rebuilt from PUBLIC_BASE_URL exactly as it was handed to Twilio. SignalWire signs differently and
    is not checked."""
    form = {key: str(value) for key, value in (await request.form()).items()}
    if settings.telephony_provider.lower() == "signalwire":
        return form
    from twilio.request_validator import RequestValidator

    signature = request.headers.get("x-twilio-signature", "")
    if not RequestValidator(settings.twilio_auth_token).validate(url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    return form


@router.post("/api/twilio/voice-webhook")
async def voice_webhook(request: Request, incident_id: str):
    """Twilio hits this once the outbound call is answered and answering machine detection has
    judged who answered. A person, or an unsure verdict, is connected to the voice agent. A
    voicemail greeting or a fax tone is hung up on and the incident recorded as unanswered."""
    form = await _signed_form(request, voice_webhook_url(incident_id))
    answered_by = form.get("AnsweredBy", "")
    if answered_by.startswith("machine") or answered_by == "fax":
        await end_unanswered_call(incident_id, form.get("CallSid", ""), "voicemail")
        return Response(content=_HANGUP_TWIML, media_type="application/xml")
    twiml = get_telephony_provider().build_stream_twiml(incident_id)
    return Response(content=twiml, media_type="application/xml")


@router.post("/api/twilio/status-callback")
async def status_callback(request: Request, incident_id: str = ""):
    """Telephony status events. The only one acted on is the final status of a call that never
    connected (busy, no answer, failed), which would otherwise leave the incident waiting forever
    on a conversation that cannot start. Answered calls are closed by the call driver."""
    if not incident_id:
        # a call placed before these callbacks named their incident
        return Response(status_code=204)
    form = await _signed_form(request, status_callback_url(incident_id))
    outcome = _NEVER_CONNECTED.get(form.get("CallStatus", ""))
    if outcome:
        await end_unanswered_call(incident_id, form.get("CallSid", ""), outcome)
    return Response(status_code=204)


@router.websocket("/ws/twilio-media/{incident_id}")
async def twilio_media_ws(websocket: WebSocket, incident_id: str):
    await websocket.accept()
    try:
        snapshot = await get_incident_snapshot(incident_id)
        state = snapshot.values
        if "gemini_authority_conversation" not in snapshot.next:
            await websocket.close()
            return

        session = AuthorityCallSession(
            websocket,
            incident_id=incident_id,
            report=state.get("report", {}),
            authority=state.get("authority", {}),
        )
        result = await session.run()
        await resume_incident(incident_id, result)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
