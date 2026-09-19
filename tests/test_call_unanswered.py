"""A dispatch call that reaches no one must never read as a dispatched team.

Seen live: a call that went to the callee's voicemail was briefed, the agent recorded a
confirmation nobody gave, and the incident closed as dispatched. These cover the guards: a call
that never connects is recorded as unanswered instead of waiting forever, and the call driver
refuses a decision recorded before anyone on the line has spoken. An unanswered incident can be
called again, including a call Twilio refuses to place at all, which is recorded the same way
rather than taking the resuming request down with it. Answering machine detection was dropped
because it hung up on people, so an answered call is always connected to the agent."""

from __future__ import annotations

import json

import httpx
import pytest
import websockets
from twilio.request_validator import RequestValidator

import agent.graph.workflow as workflow_module
import agent.voice.sip_authority_call as sip_module
from agent.auth import issue_token
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
        incident_id, {"flagged_false_positive": False, "fields": {"suspect_name": "فيصل", "suspect_id_number": "093847562"}}
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
    """Placing the call again is the team's to do, so these requests are signed in."""
    token, _ = issue_token()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.asyncio
async def test_an_unanswered_call_can_be_placed_again():
    incident_id = "TEST-RETRY-1"
    call_sid = await _calling(incident_id)

    await _twilio_post(status_callback_url(incident_id), {"CallSid": call_sid, "CallStatus": "busy"})

    snapshot = await get_incident_snapshot(incident_id)
    assert snapshot.values["status"] == "call_unanswered"
    assert snapshot.next == ("await_call_retry",)
    assert snapshot.values["authority_response"]["outcome"] == "busy"
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
async def test_a_call_the_provider_refuses_to_place_is_held_and_can_be_placed_again(monkeypatch):
    """Twilio rejecting the destination outright -- an unverified number, a country the account
    may not dial -- must not take the resuming request down with it. The report is already
    generated and sent by then, so the incident holds as a call that reached no one."""
    incident_id = "TEST-REFUSED-1"
    working = workflow_module.get_telephony_provider

    class _RefusingTelephony:
        async def place_call(self, to_number: str, incident_id: str) -> str:
            raise RuntimeError("HTTP 400 error: Unable to create record: Account not allowed to call " + to_number)

    monkeypatch.setattr(workflow_module, "get_telephony_provider", lambda: _RefusingTelephony())

    await start_incident(incident_id, "x.jpg", employee_name="سارة", employee_id="+966551234567")
    await resume_incident(incident_id, {"confirmed": True, "notes": None})
    paused = await resume_incident(
        incident_id,
        {"flagged_false_positive": False, "fields": {"suspect_name": "فيصل", "suspect_id_number": "093847562"}},
    )

    assert paused["interrupt"]["stage"] == "call_unanswered"
    snapshot = await get_incident_snapshot(incident_id)
    assert snapshot.values["status"] == "call_unanswered"
    assert snapshot.next == ("await_call_retry",)
    assert snapshot.values["call_sid"] is None
    assert snapshot.values["authority_response"]["outcome"] == "failed"
    assert snapshot.values["authority_response"]["dispatch_confirmed"] is False
    assert "Account not allowed to call" in snapshot.values["authority_response"]["error"]
    # the report survived the refused call rather than being lost with the request
    assert snapshot.values["report"] is not None

    monkeypatch.setattr(workflow_module, "get_telephony_provider", working)
    retried = await _post(f"/api/incidents/{incident_id}/call-again")
    assert retried.status_code == 200, retried.text
    assert retried.json()["interrupt"]["stage"] == "authority_conversation"
    snapshot = await get_incident_snapshot(incident_id)
    assert snapshot.values["status"] == "call_in_progress"
    assert snapshot.values["call_sid"] is not None


@pytest.mark.asyncio
async def test_an_answered_call_is_always_connected_to_the_agent():
    incident_id = "TEST-ANSWERED-1"
    call_sid = await _calling(incident_id)

    # a verdict that once hung up on people who answered, should one ever be sent again
    response = await _twilio_post(voice_webhook_url(incident_id), {"CallSid": call_sid, "AnsweredBy": "machine_start"})
    assert response.status_code == 200
    assert "<Hangup/>" not in response.text
    assert (await get_incident_snapshot(incident_id)).values["status"] == "call_in_progress"

    forged = await _twilio_post(voice_webhook_url(incident_id), {"CallSid": call_sid}, sign=False)
    assert forged.status_code == 403


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
