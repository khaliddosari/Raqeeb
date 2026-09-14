from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent import monitor
from agent.graph.runner import call_again, resume_incident
from agent.schemas import ManualSuspectInfoInput, VerificationInput

router = APIRouter(prefix="/api", tags=["verification"])


@router.post("/incidents/{incident_id}/verify")
async def verify_incident(incident_id: str, verification: VerificationInput):
    """The employee's confirm/reject decision -- a plain deterministic action, not an
    LLM call. This is the sole source of truth the graph branches on."""
    result = await resume_incident(incident_id, verification.model_dump())
    return {"incident_id": incident_id, "interrupt": result["interrupt"], "status": result["state"].get("status")}


@router.post("/incidents/{incident_id}/manual-info")
async def submit_manual_info(incident_id: str, info: ManualSuspectInfoInput):
    """Typed-form alternative to collect_incident_information's voice step. Resuming
    with all required fields present takes the graph the rest of the way in this one
    call: report generation, authority lookup, and placing the real outbound call."""
    fields = {
        "suspect_name": info.suspect_name,
        "suspect_id_number": info.suspect_id_number,
        # filler in Arabic, like everything else the report and the call carry
        "suspect_phone_number": "غير متوفر",
        "employee_notes": info.notes or "لا توجد ملاحظات إضافية",
    }
    result = await resume_incident(incident_id, {"fields": fields})
    return {"incident_id": incident_id, "interrupt": result["interrupt"], "status": result["state"].get("status")}


@router.post("/incidents/{incident_id}/call-again")
async def call_authority_again(incident_id: str):
    """Places the dispatch call again after nobody answered: a voicemail, a missed call, a busy line."""
    result = await call_again(incident_id)
    if result is None:
        raise HTTPException(status_code=409, detail="This incident is not waiting to call again.")
    return {"incident_id": incident_id, "interrupt": result["interrupt"], "status": result["state"].get("status")}
