from __future__ import annotations

import uuid

from agent.providers.base import TelephonyProvider


class MockTelephonyProvider(TelephonyProvider):
    """Simulates Twilio: 'places' a call by just handing back a fake call_sid. Used for
    local development/testing without real Twilio credentials or a public webhook URL."""

    async def place_call(self, to_number: str, incident_id: str) -> str:
        return f"MOCKCALL_{uuid.uuid4().hex[:12]}"

    def build_stream_twiml(self, incident_id: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><!-- mock: no real telephony stream --></Response>"
        )
