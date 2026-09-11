"""SignalWire implementation of TelephonyProvider. SignalWire's Compatibility API mirrors
Twilio's REST API and TwiML (LaML) format 1:1, Media Streams included -- so the TwiML we
return and the existing agent/voice/authority_call_session.py bridge work unchanged. Uses
plain httpx against the LaML REST endpoint rather than the `signalwire` PyPI package, which
pins an old `twilio` SDK version that would collide with agent/providers/twilio_telephony.py.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from agent.config import settings
from agent.providers.base import TelephonyProvider


class SignalWireTelephonyProvider(TelephonyProvider):
    async def place_call(self, to_number: str, incident_id: str) -> str:
        webhook_url = f"{settings.public_base_url}/api/twilio/voice-webhook?{urlencode({'incident_id': incident_id})}"
        status_callback = f"{settings.public_base_url}/api/twilio/status-callback"

        api_url = (
            f"https://{settings.signalwire_space_url}/api/laml/2010-04-01/"
            f"Accounts/{settings.signalwire_project_id}/Calls.json"
        )
        form_data = [
            ("To", to_number),
            ("From", settings.signalwire_phone_number),
            ("Url", webhook_url),
            ("StatusCallback", status_callback),
            ("StatusCallbackEvent", "initiated"),
            ("StatusCallbackEvent", "answered"),
            ("StatusCallbackEvent", "completed"),
        ]
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                api_url, data=form_data, auth=(settings.signalwire_project_id, settings.signalwire_token)
            )
            response.raise_for_status()
            return response.json()["sid"]

    def build_stream_twiml(self, incident_id: str) -> str:
        ws_url = f"{settings.public_base_url.replace('http', 'ws', 1)}/ws/twilio-media/{incident_id}"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Connect><Stream url="{ws_url}" /></Connect>'
            "</Response>"
        )
