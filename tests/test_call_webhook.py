"""The OpenAI realtime.call.incoming webhook, against the on-disk checkpointer that Modal runs.

The rest of the suite uses the in-memory checkpointer, which tolerates synchronous reads from
inside the event loop. AsyncSqliteSaver does not: it raises InvalidStateError, so the webhook
returned 500, OpenAI's call was never accepted, and the authority call died after dialling.
This drives the real route, signed the way OpenAI signs it, over the on-disk saver."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import agent.graph.workflow as workflow_module
import agent.routes.openai_routes as openai_routes
from agent.config import settings
from agent.db import init_db
from agent.graph.runner import resume_incident, start_incident
from agent.main import app
from agent.schemas import DetectionResult

_SECRET = b"raqeeb-test-webhook-secret"


class _FakeDetector:
    def detect(self, image_path: str, annotate: bool = False) -> DetectionResult:
        return DetectionResult(detected_class="Gun", confidence=0.91)


def _signed(body: bytes) -> dict[str, str]:
    webhook_id, timestamp = "wh_test_1", str(int(time.time()))
    digest = hmac.new(_SECRET, f"{webhook_id}.{timestamp}.{body.decode()}".encode(), hashlib.sha256).digest()
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": "v1," + base64.b64encode(digest).decode(),
        "content-type": "application/json",
    }


@pytest.mark.asyncio
async def test_incoming_call_webhook_accepts_with_on_disk_checkpoints(tmp_path, monkeypatch):
    init_db()
    monkeypatch.setattr(workflow_module, "get_detector", lambda: _FakeDetector())
    monkeypatch.setattr(settings, "openai_webhook_secret", "whsec_" + base64.b64encode(_SECRET).decode())

    accepted: dict = {}

    async def fake_accept(call_id, incident_id, report):
        accepted.update(call_id=call_id, incident_id=incident_id, report=report)

    async def fake_observe(call_id, incident_id):
        return None

    monkeypatch.setattr(openai_routes, "accept_call", fake_accept)
    monkeypatch.setattr(openai_routes, "observe_and_drive", fake_observe)

    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.db")) as saver:
        await saver.setup()
        monkeypatch.setattr(workflow_module, "_compiled", workflow_module.build_graph().compile(checkpointer=saver))

        incident_id = "TEST-SIP-WEBHOOK-1"
        await start_incident(incident_id, "x.jpg", employee_name="Sara", employee_id="+966551234567")
        await resume_incident(incident_id, {"confirmed": True, "notes": None})
        paused = await resume_incident(
            incident_id,
            {"flagged_false_positive": False, "fields": {"suspect_name": "John Doe", "suspect_id_number": "X123"}},
        )
        assert paused["interrupt"]["stage"] == "authority_conversation"

        event = {
            "type": "realtime.call.incoming",
            "data": {"call_id": "rtc_test_1", "sip_headers": [{"name": "X-Incident-Id", "value": incident_id}]},
        }
        body = json.dumps(event).encode()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/openai/webhook", content=body, headers=_signed(body))

    assert response.status_code == 200, response.text
    assert accepted["call_id"] == "rtc_test_1"
    assert accepted["incident_id"] == incident_id
    assert accepted["report"]["detected_item"] == "Gun"
