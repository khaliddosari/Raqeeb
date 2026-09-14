"""Twilio implementation of TelephonyProvider. Twilio is telephony only -- it places the
call; all conversational intelligence lives in the LLM_PROVIDER-selected model. How
Twilio's audio reaches that model differs by provider: for LLM_PROVIDER=openai, the
call is bridged directly to OpenAI's SIP connector (agent/voice/sip_authority_call.py)
so audio never touches our server; otherwise it's streamed to our own Media Stream
WebSocket (agent/voice/authority_call_session.py), which bridges it to the model.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from agent.config import settings
from agent.providers.base import TelephonyProvider


def _client():
    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


# Twilio signs each webhook over the exact URL it was given, so the routes that check those
# signatures (agent/routes/twilio_routes.py) rebuild the URL with these same two functions.
def voice_webhook_url(incident_id: str) -> str:
    return f"{settings.public_base_url}/api/twilio/voice-webhook?{urlencode({'incident_id': incident_id})}"


def status_callback_url(incident_id: str) -> str:
    return f"{settings.public_base_url}/api/twilio/status-callback?{urlencode({'incident_id': incident_id})}"


class TwilioTelephonyProvider(TelephonyProvider):
    async def place_call(self, to_number: str, incident_id: str) -> str:
        import asyncio

        def _create():
            call = _client().calls.create(
                to=to_number,
                from_=settings.twilio_phone_number,
                url=voice_webhook_url(incident_id),
                status_callback=status_callback_url(incident_id),
                # "completed" also reports calls that never connected: busy, no-answer, failed.
                status_callback_event=["initiated", "answered", "completed"],
                # Answering machine detection, synchronous: Twilio holds the voice webhook until it
                # has judged who picked up and says so in AnsweredBy, so a voicemail greeting is
                # hung up on instead of being briefed, and never mistaken for the authority.
                machine_detection="Enable",
            )
            return call.sid

        return await asyncio.to_thread(_create)

    def build_stream_twiml(self, incident_id: str) -> str:
        # No <Say> preamble -- the callee should hear the agent's own live greeting as
        # the very first thing on the line, not a canned Twilio announcement first.
        if settings.llm_provider.lower() == "openai":
            return self._build_sip_twiml(incident_id)
        ws_url = f"{settings.public_base_url.replace('http', 'ws', 1)}/ws/twilio-media/{incident_id}"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Connect><Stream url="{ws_url}" /></Connect>'
            "</Response>"
        )

    def _build_sip_twiml(self, incident_id: str) -> str:
        # X-Incident-Id rides along on the SIP INVITE Twilio sends to OpenAI, so our
        # realtime.call.incoming webhook (agent/routes/openai_routes.py) can match the
        # call back to this incident -- OpenAI has no other way to know which incident
        # a given inbound SIP session is for.
        sip_uri = (
            f"sip:{settings.openai_project_id}@sip.api.openai.com;transport=tls"
            f"?X-Incident-Id={quote(incident_id)}"
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"<Dial><Sip>{sip_uri}</Sip></Dial>"
            "</Response>"
        )
