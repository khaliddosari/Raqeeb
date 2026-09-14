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


class ManualSuspectInfoInput(BaseModel):
    """A typed-form alternative to the voice-collection step, for demos/presentations
    where talking to the mic isn't practical. suspect_phone_number and notes aren't
    asked for -- the report still requires them, so a placeholder fills the gap."""

    suspect_name: str
    suspect_id_number: str
    notes: str | None = None
    # From a scanned pass: the event it was issued for, which replaces the location stamped at
    # detection, so the report and the call carry that event's scenario.
    location: str | None = None


class AuthorityCallResult(BaseModel):
    dispatch_confirmed: bool
    authority_statement: str
    raw_transcript: list[dict[str, str]] = []


class AuthorityConfig(BaseModel):
    name: str
    # The same authority named in Arabic, for the call and the Arabic dashboard.
    name_ar: str | None = None
    # Which real agency this is, independent of the unit named above; the dashboard uses it
    # to show that agency's mark.
    agency: Literal["police", "airport_security"] | None = None
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
    # the checkpoint's demo scenario, ordered label to detail, from agent/checkpoints.py
    scenario: dict[str, str] = {}
    severity: str
    recommended_action: str
    additional_info: dict[str, Any] = {}
