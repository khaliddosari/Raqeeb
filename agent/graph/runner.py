"""Thin driver around the compiled graph: start/resume a thread, pull out the pending
interrupt payload (if any) for the caller to act on, and persist the resulting state to
the database (Incident + AuditLog) after every step."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from langgraph.types import Command

from agent import monitor
from agent.config import settings
from agent.db import SessionLocal
from agent.graph.workflow import get_compiled_graph, thread_config
from agent.models import AuditLog, Incident


# Outcomes of a dispatch call that never reached a person. They leave the incident unreported, and
# the dashboard offers to call again. Answered calls carry outcome "answered".
UNANSWERED_OUTCOMES = frozenset({"voicemail", "no_answer", "busy", "failed"})

# One resume at a time per incident on the call paths: Twilio's webhooks and the retry request
# arrive independently and must not both move the same paused call on.
_call_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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
    call_transport: str = "phone",
) -> dict[str, Any]:
    """The on-duty employee (from their shift login) and the checkpoint's location are
    stamped onto the incident right here, before detection even runs -- the employee
    only ever fills in the suspect's details, never re-types who or where they are.

    location falls back to the configured checkpoint. call_phone, already validated and in
    E.164, replaces the authority's number as the destination of the dispatch call.
    call_transport "browser" holds that conversation in the dashboard instead of placing one."""
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
    initial_state["call_transport"] = call_transport
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


async def get_incident_snapshot(incident_id: str):
    """Async on purpose. The on-disk AsyncSqliteSaver refuses synchronous reads from the event
    loop it runs on, which is where every route runs, so get_state() raised InvalidStateError
    and the OpenAI call webhook returned 500. Compiling here too means a request that lands on
    a freshly started container still finds its incident in the checkpoint."""
    return await (await get_compiled_graph()).aget_state(thread_config(incident_id))


async def end_unanswered_call(incident_id: str, call_sid: str, outcome: str, *, wait_seconds: float = 5.0) -> bool:
    """Closes the dispatch call as unanswered, if the incident is still waiting on that very call.

    A webhook naming any other call is ignored: a late event from an earlier attempt must not end
    the retry. The wait covers a call that fails the moment it is placed, whose event can arrive
    before the graph has checkpointed the call it is waiting on. Returns whether it resumed."""
    assert outcome in UNANSWERED_OUTCOMES, outcome
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds
    async with _call_locks[incident_id]:
        while True:
            snapshot = await get_incident_snapshot(incident_id)
            waiting = snapshot.next == ("gemini_authority_conversation",)
            if waiting and call_sid and snapshot.values.get("call_sid") == call_sid:
                await resume_incident(
                    incident_id,
                    {"dispatch_confirmed": False, "outcome": outcome, "authority_statement": "", "raw_transcript": []},
                )
                return True
            if waiting or loop.time() >= deadline:
                return False
            await asyncio.sleep(0.25)


async def call_again(incident_id: str) -> dict[str, Any] | None:
    """Places the dispatch call again after an unanswered one. None if the incident is not waiting for that."""
    async with _call_locks[incident_id]:
        snapshot = await get_incident_snapshot(incident_id)
        if snapshot.next != ("await_call_retry",):
            return None
        return await resume_incident(incident_id, {"retry": True})
