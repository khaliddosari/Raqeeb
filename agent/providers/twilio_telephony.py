"""Twilio implementation of TelephonyProvider. Twilio is telephony only -- it places the
call and streams raw audio; all conversational intelligence lives in Gemini
(agent/voice/authority_call_session.py), which is bridged to the call's Media Stream.
"""

from __future__ import annotations

from urllib.parse import urlencode

from agent.config import settings
from agent.providers.base import TelephonyProvider


def _client():
    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


class TwilioTelephonyProvider(TelephonyProvider):
    async def place_call(self, to_number: str, incident_id: str) -> str:
        import asyncio

        webhook_url = f"{settings.public_base_url}/api/twilio/voice-webhook?{urlencode({'incident_id': incident_id})}"
        status_callback = f"{settings.public_base_url}/api/twilio/status-callback"

        def _create():
            call = _client().calls.create(
                to=to_number,
                from_=settings.twilio_phone_number,
                url=webhook_url,
                status_callback=status_callback,
                status_callback_event=["initiated", "answered", "completed"],
            )
            return call.sid

        return await asyncio.to_thread(_create)

    def build_stream_twiml(self, incident_id: str) -> str:
        ws_url = f"{settings.public_base_url.replace('http', 'ws', 1)}/ws/twilio-media/{incident_id}"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>Connecting you to Raqeeb.</Say>"
            f'<Connect><Stream url="{ws_url}" /></Connect>'
            "</Response>"
        )
