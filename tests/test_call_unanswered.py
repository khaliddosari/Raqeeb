"""A dispatch call that reaches no one must never read as a dispatched team.

Seen live: a call that went to the callee's voicemail was briefed, the agent recorded a
confirmation nobody gave, and the incident closed as dispatched. These cover the three guards:
Twilio's answering machine detection hangs up on a machine, a call that never connects is
recorded as unanswered instead of waiting forever, and the call driver refuses a decision
recorded before anyone on the line has spoken. An unanswered incident can be called again."""

from __future__ import annotations

import json

import httpx
import pytest
import websockets
from twilio.request_validator import RequestValidator

import agent.graph.workflow as workflow_module
import agent.voice.sip_authority_call as sip_module
from agent.config import settings
from agent.db import init_db
from agent.graph.runner import get_incident_snapshot, resume_incident, start_incident
from agent.main import app
from agent.providers.twilio_telephony import status_callback_url, voice_webhook_url
from agent.schemas import DetectionResult


class _FakeDetector:
    def detect(self, image_path: str, annotate: bool = False) -> DetectionResult:
        return DetectionResult(detected_class="Gun", confidence=0.91)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(workflow_module, "get_detector", lambda: _FakeDetector())
    init_db()


async def _calling(incident_id: str) -> str:
    """Runs an incident up to the dispatch call and returns the placed call's SID."""
    await start_incident(incident_id, "x.jpg", employee_name="سارة", employee_id="+966551234567")
    await resume_incident(incident_id, {"confirmed": True, "notes": None})
    paused = await resume_incident(
        incident_id, {"flagged_false_positive": False, "fields": {"suspect_name": "فيصل", "suspect_id_number": "1093847562"}}
    )
    assert paused["interrupt"]["stage"] == "authority_conversation"
    return paused["state"]["call_sid"]


async def _twilio_post(url: str, form: dict[str, str], *, sign: bool = True) -> httpx.Response:
    """Posts a webhook the way Twilio does: form-encoded, signed over the URL it was given."""
    signature = RequestValidator(settings.twilio_auth_token).compute_signature(url, form) if sign else "forged"
    path = url.removeprefix(settings.public_base_url)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, data=form, headers={"X-Twilio-Signature": signature})


async def _post(path: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path)


@pytest.mark.asyncio
async def test_voicemail_is_hung_up_on_and_the_call_can_be_placed_again():
    incident_id = "TEST-VOICEMAIL-1"
    call_sid = await _calling(incident_id)

    response = await _twilio_post(voice_webhook_url(incident_id), {"CallSid": call_sid, "AnsweredBy": "machine_start"})
    assert response.status_code == 200
    assert "<Hangup/>" in response.text

    snapshot = await get_incident_snapshot(incident_id)
    assert snapshot.values["status"] == "call_unanswered"
    assert snapshot.next == ("await_call_retry",)
    assert snapshot.values["authority_response"]["outcome"] == "voicemail"
    assert snapshot.values["authority_response"]["dispatch_confirmed"] is False

    retried = await _post(f"/api/incidents/{incident_id}/call-again")
    assert retried.status_code == 200, retried.text
    assert retried.json()["interrupt"]["stage"] == "authority_conversation"
    snapshot = await get_incident_snapshot(incident_id)
    assert snapshot.values["status"] == "call_in_progress"
    assert snapshot.values["call_sid"] != call_sid
    assert snapshot.values["authority_response"] is None

    # only an unanswered incident can be called again
    assert (await _post(f"/api/incidents/{incident_id}/call-again")).status_code == 409


@pytest.mark.asyncio
async def test_a_person_answering_is_connected_to_the_agent():
    incident_id = "TEST-HUMAN-1"
    call_sid = await _calling(incident_id)

    response = await _twilio_post(voice_webhook_url(incident_id), {"CallSid": call_sid, "AnsweredBy": "human"})
    assert response.status_code == 200
    assert "<Hangup/>" not in response.text
    assert (await get_incident_snapshot(incident_id)).values["status"] == "call_in_progress"


@pytest.mark.asyncio
async def test_a_missed_call_is_recorded_and_stale_or_forged_callbacks_are_ignored():
    incident_id = "TEST-NO-ANSWER-1"
    call_sid = await _calling(incident_id)
    url = status_callback_url(incident_id)

    forged = await _twilio_post(url, {"CallSid": call_sid, "CallStatus": "no-answer"}, sign=False)
    assert forged.status_code == 403

    # a late event from an earlier attempt names another call
    await _twilio_post(url, {"CallSid": "CA_an_earlier_call", "CallStatus": "no-answer"})
    assert (await get_incident_snapshot(incident_id)).values["status"] == "call_in_progress"

    # the answered leg ending is the call driver's to close, not this callback's
    await _twilio_post(url, {"CallSid": call_sid, "CallStatus": "completed"})
    assert (await get_incident_snapshot(incident_id)).values["status"] == "call_in_progress"

    response = await _twilio_post(url, {"CallSid": call_sid, "CallStatus": "no-answer"})
    assert response.status_code == 204
    snapshot = await get_incident_snapshot(incident_id)
    assert snapshot.values["status"] == "call_unanswered"
    assert snapshot.values["authority_response"]["outcome"] == "no_answer"


class _FakeRealtime:
    """The Realtime call websocket, replaying scripted server events and keeping what is sent."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.sent: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._replay()

    async def _replay(self):
        for event in self.events:
            yield json.dumps(event)

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


def _decision(call_id: str, confirmed: bool, statement: str) -> dict:
    return {
        "type": "response.function_call_arguments.done",
        "name": "record_dispatch_confirmation",
        "call_id": call_id,
        "arguments": json.dumps({"confirmed": confirmed, "statement": statement}, ensure_ascii=False),
    }


async def _drive(monkeypatch, events: list[dict]) -> tuple[dict, _FakeRealtime]:
    realtime = _FakeRealtime(events)
    resumed: dict = {}

    async def fake_resume(incident_id, result):
        resumed.update(result)

    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: realtime)
    monkeypatch.setattr(sip_module, "resume_incident", fake_resume)
    await sip_module.observe_and_drive("rtc_test", "TEST-GUARD-1")
    return resumed, realtime


def _tool_outputs(realtime: _FakeRealtime) -> dict[str, dict]:
    return {
        sent["item"]["call_id"]: json.loads(sent["item"]["output"])
        for sent in realtime.sent
        if sent.get("type") == "conversation.item.create"
    }


@pytest.mark.asyncio
async def test_a_decision_recorded_before_anyone_speaks_is_refused(monkeypatch):
    result, realtime = await _drive(monkeypatch, [_decision("c1", True, "تمت الموافقة على إرسال الفريق")])

    assert result["dispatch_confirmed"] is False
    assert result["authority_statement"] == ""
    assert _tool_outputs(realtime)["c1"]["recorded"] is False


@pytest.mark.asyncio
async def test_a_decision_after_the_authority_replies_is_recorded(monkeypatch):
    result, realtime = await _drive(
        monkeypatch,
        [
            _decision("c1", True, "مبكر"),
            {"type": "input_audio_buffer.committed", "item_id": "a1"},
            {"type": "conversation.item.input_audio_transcription.completed", "item_id": "a1", "transcript": "نعم نرسل فريق"},
            _decision("c2", True, "نعم نرسل فريق"),
        ],
    )

    assert result["dispatch_confirmed"] is True
    assert result["outcome"] == "answered"
    assert result["authority_statement"] == "نعم نرسل فريق"
    outputs = _tool_outputs(realtime)
    assert outputs["c1"]["recorded"] is False
    assert outputs["c2"] == {"acknowledged": True}
