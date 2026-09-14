from __future__ import annotations

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect

from agent.graph.runner import get_incident_snapshot, resume_incident
from agent.providers.factory import get_telephony_provider
from agent.voice.authority_call_session import AuthorityCallSession

router = APIRouter(tags=["twilio"])


@router.post("/api/twilio/voice-webhook")
async def voice_webhook(incident_id: str):
    """Twilio hits this once the outbound call is answered. We reply with TwiML that
    connects the call's audio to our media-stream websocket for this incident."""
    twiml = get_telephony_provider().build_stream_twiml(incident_id)
    return Response(content=twiml, media_type="application/xml")


@router.post("/api/twilio/status-callback")
async def status_callback(request: Request):
    # Telephony status events only (ringing/answered/completed) -- no reasoning here.
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
