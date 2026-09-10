from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent.config import settings
from agent.graph.runner import get_incident_snapshot, resume_incident
from agent.report import missing_required_fields
from agent.voice.employee_session import EmployeeVoiceSession

router = APIRouter(tags=["voice"])


@router.websocket("/ws/employee/{incident_id}")
async def employee_voice_ws(websocket: WebSocket, incident_id: str):
    await websocket.accept()
    try:
        while True:
            snapshot = get_incident_snapshot(incident_id)
            state = snapshot.values
            if "collect_incident_information" not in snapshot.next:
                await websocket.send_json({"type": "not_awaiting_voice", "status": state.get("status")})
                break

            session = EmployeeVoiceSession(
                websocket,
                detection_class=state["detection_class"],
                detection_confidence=state["detection_confidence"],
                required_fields=list(settings.required_incident_fields),
                already_collected=state.get("incident_data", {}),
            )
            answer = await session.run()
            result = await resume_incident(incident_id, answer)

            if answer.get("flagged_false_positive"):
                await websocket.send_json({"type": "workflow_ended", "status": "false_positive"})
                break

            new_stage = (result["interrupt"] or {}).get("stage")
            if new_stage == "collect_information":
                # validate_information found gaps; loop and keep talking to the employee.
                still_missing = missing_required_fields(result["state"].get("incident_data", {}))
                await websocket.send_json({"type": "more_info_needed", "missing": still_missing})
                continue

            await websocket.send_json({"type": "collection_complete", "next_stage": new_stage})
            break
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
