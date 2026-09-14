"""End-to-end exercise of the whole LangGraph workflow with LLM_PROVIDER=mock and
TELEPHONY_PROVIDER=mock (see conftest.py) -- no real YOLO weights, Gemini, or Twilio
credentials needed. Confirms: detection fields are never mutated after being set,
the employee's verification decision alone gates the false_positive branch, missing
fields loop the collection step, and the graph reaches END with a full report and an
authority dispatch confirmation."""

from __future__ import annotations

import pytest

import agent.graph.workflow as workflow_module
from agent.db import init_db
from agent.graph.runner import resume_incident, start_incident
from agent.schemas import DetectionResult


class _FakeDetector:
    # annotate is accepted and ignored: the graph asks for a boxed render, which is a
    # rendering side effect the workflow does not depend on.
    def detect(self, image_path: str, annotate: bool = False) -> DetectionResult:
        return DetectionResult(detected_class="Knife", confidence=0.87)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(workflow_module, "get_detector", lambda: _FakeDetector())
    init_db()


@pytest.mark.asyncio
async def test_confirmed_detection_runs_to_closed():
    incident_id = "TEST-CONFIRMED-1"

    result = await start_incident(incident_id, "irrelevant.jpg", employee_name="Sara", employee_id="E123")
    assert result["interrupt"]["stage"] == "employee_verification"
    assert result["state"]["detection_class"] == "Knife"
    assert result["state"]["detection_confidence"] == 0.87
    # location + on-duty employee are stamped in at start, before verification even runs.
    assert result["state"]["incident_data"]["location"]
    assert result["state"]["incident_data"]["employee_name"] == "Sara"

    result = await resume_incident(incident_id, {"confirmed": True, "notes": None})
    assert result["interrupt"]["stage"] == "collect_information"
    # employee_name/id/location are seeded automatically -- already collected, so the
    # voice session's "still needed" list never asks for them again.
    already_collected = result["interrupt"]["already_collected"]
    assert already_collected["location"]
    assert already_collected["employee_name"] == "Sara"

    # Deliberately omit one required field first, to exercise the validate -> loop-back edge.
    partial_fields = {"suspect_name": "John Doe"}
    result = await resume_incident(incident_id, {"flagged_false_positive": False, "fields": partial_fields})
    assert result["interrupt"]["stage"] == "collect_information"  # looped back, still missing fields

    remaining_fields = {"suspect_id_number": "X123"}
    result = await resume_incident(incident_id, {"flagged_false_positive": False, "fields": remaining_fields})
    assert result["interrupt"]["stage"] == "authority_conversation"

    state = result["state"]
    assert state["detection_class"] == "Knife"  # untouched by everything downstream
    assert state["detection_confidence"] == 0.87
    assert state["report"]["detected_item"] == "Knife"
    assert state["report"]["verification_status"] == "confirmed"
    assert state["call_sid"].startswith("MOCKCALL_")
    assert state["authority"]["name"]

    result = await resume_incident(
        incident_id, {"dispatch_confirmed": True, "authority_statement": "Team dispatched", "raw_transcript": []}
    )
    assert result["interrupt"] is None
    assert result["state"]["status"] == "closed"


@pytest.mark.asyncio
async def test_employee_mobile_takes_the_call_and_location_is_stamped():
    incident_id = "TEST-CALL-PHONE-1"

    await start_incident(
        incident_id,
        "irrelevant.jpg",
        employee_name="Sara",
        employee_id="+966551234567",
        location="Black Hat MEA",
        call_phone="+966551234567",
    )
    await resume_incident(incident_id, {"confirmed": True, "notes": None})
    result = await resume_incident(
        incident_id,
        {"flagged_false_positive": False, "fields": {"suspect_name": "John Doe", "suspect_id_number": "X123"}},
    )

    state = result["state"]
    assert state["incident_data"]["location"] == "Black Hat MEA"
    assert state["report"]["location"] == "Black Hat MEA"
    # the checkpoint's scenario travels with the report, for the narrative and the call
    assert state["report"]["scenario"]["نقطة التفتيش"] == "بوابة المشاركين رقم 2"
    # the call goes to the employee, but the agency it represents is still the mapped one
    assert state["authority"]["phone_number"] == "+966551234567"
    assert state["authority"]["agency"] == "police"


@pytest.mark.asyncio
async def test_false_positive_via_dashboard_button_ends_workflow():
    incident_id = "TEST-FALSEPOS-1"

    await start_incident(incident_id, "irrelevant.jpg", employee_name="Sara", employee_id="E123")
    result = await resume_incident(incident_id, {"confirmed": False, "notes": "not a real knife"})

    assert result["interrupt"] is None  # reached END, nothing left to resume
    assert result["state"]["status"] == "false_positive"
    assert result["state"]["detection_class"] == "Knife"  # detection itself is preserved, just not acted on


@pytest.mark.asyncio
async def test_false_positive_flagged_during_voice_collection():
    incident_id = "TEST-FALSEPOS-VOICE-1"

    await start_incident(incident_id, "irrelevant.jpg", employee_name="Ali", employee_id="E999")
    await resume_incident(incident_id, {"confirmed": True, "notes": None})

    result = await resume_incident(incident_id, {"flagged_false_positive": True, "fields": {}})

    assert result["interrupt"] is None
    assert result["state"]["status"] == "false_positive"
    assert result["state"]["verification_status"] == "false_positive"
