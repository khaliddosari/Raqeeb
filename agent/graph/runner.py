"""Thin driver around the compiled graph: start/resume a thread, pull out the pending
interrupt payload (if any) for the caller to act on, and persist the resulting state to
the database (Incident + AuditLog) after every step."""

from __future__ import annotations

from typing import Any

from langgraph.types import Command

from agent import monitor
from agent.config import settings
from agent.db import SessionLocal
from agent.graph.workflow import get_compiled_graph, thread_config
from agent.models import AuditLog, Incident


def _extract_interrupt(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value


def _sync_db(incident_id: str, state: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        incident = db.get(Incident, incident_id)
        if incident is None:
            incident = Incident(
                id=incident_id,
                detection_class=state.get("detection_class", ""),
                detection_confidence=state.get("detection_confidence", 0.0),
                image_path=state.get("image_path", ""),
            )
            db.add(incident)

        incident.status = state.get("status", incident.status)
        incident.verification_status = state.get("verification_status")
        incident.verification_channel = state.get("verification_channel")
        incident.employee_name = state.get("employee_name")
        incident.employee_id = state.get("employee_id")
        incident.incident_data = state.get("incident_data", {})
        incident.report_json = state.get("report")
        incident.report_summary = state.get("report_summary")
        authority = state.get("authority") or {}
        incident.authority_name = authority.get("name")
        incident.authority_phone = authority.get("phone_number")
        incident.call_sid = state.get("call_sid")
        incident.authority_response = state.get("authority_response")

        db.add(
            AuditLog(
                incident_id=incident_id,
                stage=state.get("status", "unknown"),
                detail={k: v for k, v in state.items() if k not in ("incident_data", "__interrupt__")},
            )
        )
        db.commit()
        monitor.publish_status(
            incident_id,
            incident.status,
            detection_class=incident.detection_class,
            authority_name=incident.authority_name,
            call_sid=incident.call_sid,
        )
    finally:
        db.close()


async def start_incident(
    incident_id: str,
    image_path: str,
    *,
    employee_name: str,
    employee_id: str,
    location: str | None = None,
    call_phone: str | None = None,
) -> dict[str, Any]:
    """The on-duty employee (from their shift login) and the checkpoint's location are
    stamped onto the incident right here, before detection even runs -- the employee
    only ever fills in the suspect's details, never re-types who or where they are.

    location falls back to the configured checkpoint. call_phone, already validated and in
    E.164, replaces the authority's number as the destination of the dispatch call."""
    config = thread_config(incident_id)
    initial_state = {
        "incident_id": incident_id,
        "image_path": image_path,
        "employee_name": employee_name,
        "employee_id": employee_id,
        "incident_data": {
            "location": location or settings.checkpoint_location,
            "employee_name": employee_name,
            "employee_id": employee_id,
        },
    }
    if call_phone:
        initial_state["call_phone"] = call_phone
    result = await (await get_compiled_graph()).ainvoke(initial_state, config)
    _sync_db(incident_id, result)
    return {"state": result, "interrupt": _extract_interrupt(result)}


async def resume_incident(incident_id: str, resume_value: Any) -> dict[str, Any]:
    config = thread_config(incident_id)
    result = await (await get_compiled_graph()).ainvoke(Command(resume=resume_value), config)
    _sync_db(incident_id, result)
    return {"state": result, "interrupt": _extract_interrupt(result)}


def get_incident_snapshot(incident_id: str):
    from agent.graph import workflow

    if workflow._compiled is None:
        raise RuntimeError("graph not initialised yet; no incident can exist")
    return workflow._compiled.get_state(thread_config(incident_id))
