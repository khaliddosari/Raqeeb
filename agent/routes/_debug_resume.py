"""Temporary manual-testing endpoint. Lets us drive collect_incident_information without
going through the real voice WebSocket, to test the downstream report/authority-call
steps directly. Not part of the product -- delete after testing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agent.config import settings
from agent.graph.runner import _extract_interrupt, _sync_db, resume_incident
from agent.graph.workflow import compiled_graph, thread_config

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.post("/start/{incident_id}")
async def debug_start(incident_id: str, payload: dict[str, Any]):
    """Seeds detection_class/confidence directly, skipping real YOLO inference --
    for testing on memory-constrained hosts where loading torch/ultralytics OOMs."""
    config = thread_config(incident_id)
    initial_state = {
        "incident_id": incident_id,
        "image_path": "debug",
        "employee_name": payload["employee_name"],
        "employee_id": payload["employee_id"],
        "detection_class": payload["detection_class"],
        "detection_confidence": payload["detection_confidence"],
        "incident_data": {
            "location": settings.checkpoint_location,
            "employee_name": payload["employee_name"],
            "employee_id": payload["employee_id"],
        },
    }
    result = await compiled_graph.ainvoke(initial_state, config)
    _sync_db(incident_id, result)
    return {"interrupt": _extract_interrupt(result), "state": result}


@router.post("/resume/{incident_id}")
async def debug_resume(incident_id: str, payload: dict[str, Any]):
    result = await resume_incident(incident_id, payload)
    return {"interrupt": result["interrupt"], "state": result["state"]}


@router.post("/test-stream-webhook")
async def test_stream_webhook():
    """Pure connectivity probe: one-way <Start><Stream> (doesn't take over the call)
    followed by <Say>/<Pause> so the call stays up regardless of whether the stream
    connects. Used to test whether Twilio's Media Streams infra can reach us at all,
    independent of <Connect><Stream>'s stricter bidirectional requirements."""
    ws_url = f"{settings.public_base_url.replace('http', 'ws', 1)}/ws/twilio-media/diagnostic"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Start><Stream url="{ws_url}" /></Start>'
        "<Say>Testing one way stream connection.</Say>"
        '<Pause length="5"/>'
        "<Say>Test complete, goodbye.</Say>"
        "</Response>"
    )
    from fastapi import Response

    return Response(content=twiml, media_type="application/xml")
