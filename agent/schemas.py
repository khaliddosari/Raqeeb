from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class DetectionResult(BaseModel):
    """Immutable YOLO output. Nothing downstream may change these two fields."""

    detected_class: str
    confidence: float


class VerificationInput(BaseModel):
    """Submitted by the employee dashboard (button click), not by an LLM. The employee's
    identity is already known from their shift login and location from the checkpoint
    config -- this only ever carries their confirm/reject decision plus optional notes."""

    confirmed: bool
    notes: str | None = None


class CollectedInfoInput(BaseModel):
    """What the Gemini voice-collection session hands back to the graph on resume."""

    flagged_false_positive: bool = False
    fields: dict[str, Any] = {}


class AuthorityCallResult(BaseModel):
    dispatch_confirmed: bool
    authority_statement: str
    raw_transcript: list[dict[str, str]] = []


class AuthorityConfig(BaseModel):
    name: str
    phone_number: str
    report_endpoint: str
    endpoint_type: Literal["webhook", "email", "api"] = "webhook"
    default_severity: Literal["low", "medium", "high", "critical"] = "medium"


class IncidentReport(BaseModel):
    incident_id: str
    date_time: str
    location: str
    detected_item: str
    yolo_confidence: float
    verification_status: str
    suspect: dict[str, Any]
    employee: dict[str, Any]
    inspection_notes: str
    severity: str
    recommended_action: str
    additional_info: dict[str, Any] = {}
