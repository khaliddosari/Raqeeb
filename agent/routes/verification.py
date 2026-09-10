from __future__ import annotations

from fastapi import APIRouter

from agent.graph.runner import resume_incident
from agent.schemas import VerificationInput

router = APIRouter(prefix="/api", tags=["verification"])


@router.post("/incidents/{incident_id}/verify")
async def verify_incident(incident_id: str, verification: VerificationInput):
    """The employee's confirm/reject decision -- a plain deterministic action, not an
    LLM call. This is the sole source of truth the graph branches on."""
    result = await resume_incident(incident_id, verification.model_dump())
    return {"incident_id": incident_id, "interrupt": result["interrupt"], "status": result["state"].get("status")}
