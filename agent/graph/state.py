"""LangGraph state for one incident. `detection_class`/`detection_confidence` are only
ever written by yolo_detection_node -- no other node in workflow.py returns those keys,
so nothing downstream (including Gemini) can alter them even by accident."""

from __future__ import annotations

from typing import Any, TypedDict


class IncidentState(TypedDict, total=False):
    incident_id: str
    image_path: str
    status: str

    # Written once, by yolo_detection_node only.
    detection_class: str
    detection_confidence: float

    # Employee's decision -- the sole source of truth for confirmed/false_positive.
    verification_status: str  # "confirmed" | "false_positive"
    verification_channel: str  # "dashboard_button" | "voice"
    employee_name: str
    employee_id: str

    incident_data: dict[str, Any]

    report: dict[str, Any]
    report_summary: str

    authority: dict[str, Any]
    # The on-duty employee's mobile, when given: the dispatch call goes here instead of
    # the authority's configured number.
    call_phone: str

    # "phone": the telephony provider dials call_phone (the team's own dashboard).
    # "browser": the visitor holds the conversation in their own browser over WebRTC, and
    # agent/routes/browser_call.py resumes the same interrupt with the same result shape.
    call_transport: str

    call_sid: str
    authority_response: dict[str, Any]
