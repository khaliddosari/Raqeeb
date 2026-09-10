"""Temporary manual-testing endpoint. Lets us drive collect_incident_information without
going through the real voice WebSocket, to test the downstream report/authority-call
steps directly. Not part of the product -- delete after testing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agent.graph.runner import resume_incident

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.post("/resume/{incident_id}")
async def debug_resume(incident_id: str, payload: dict[str, Any]):
    result = await resume_incident(incident_id, payload)
    return {"interrupt": result["interrupt"], "state": result["state"]}
