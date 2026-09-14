"""Report validation and generation. Reads detection/verification data but never writes
to it -- this module only ever produces new fields (report_json, summary), it can't
touch detected_class/confidence/verification_status.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from agent.checkpoints import scenario_for
from agent.config import settings
from agent.providers.base import LLMProvider
from agent.schemas import IncidentReport


# Checkpoint local time. Saudi Arabia is UTC+3 year round and has never observed DST,
# so a fixed offset is exact here and avoids depending on the IANA database being
# present, which Windows does not ship by default.
RIYADH = datetime.timezone(datetime.timedelta(hours=3), "AST")


def checkpoint_now() -> datetime.datetime:
    """Local time at the checkpoint. Incident ids and report timestamps use this, so an
    incident opened at 01:00 Riyadh is filed under that date rather than the previous
    UTC one. Stored created_at/updated_at columns stay UTC."""
    return datetime.datetime.now(RIYADH)


def new_incident_id() -> str:
    return f"INC-{checkpoint_now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def missing_required_fields(incident_data: dict[str, Any]) -> list[str]:
    return [f for f in settings.required_incident_fields if not incident_data.get(f)]


async def generate_report(
    *,
    incident_id: str,
    detection_class: str,
    detection_confidence: float,
    verification_status: str,
    incident_data: dict[str, Any],
    llm: LLMProvider,
) -> tuple[IncidentReport, str]:
    """Builds the structured report, then asks Gemini only for the narrative summary
    and a severity/action suggestion -- never for the detection or verification fields,
    which are copied through verbatim from state."""

    missing = missing_required_fields(incident_data)
    if missing:
        raise ValueError(f"Cannot generate report, missing fields: {missing}")

    report_dict = {
        "incident_id": incident_id,
        "date_time": checkpoint_now().isoformat(),
        "location": incident_data["location"],
        "detected_item": detection_class,
        "yolo_confidence": detection_confidence,
        "verification_status": verification_status,
        "suspect": {
            "name": incident_data.get("suspect_name"),
            "id_number": incident_data.get("suspect_id_number"),
            "phone_number": incident_data.get("suspect_phone_number"),
        },
        "employee": {
            "name": incident_data.get("employee_name"),
            "id": incident_data.get("employee_id"),
        },
        "inspection_notes": incident_data.get("employee_notes", ""),
        "scenario": scenario_for(incident_data["location"]),
        "additional_info": {
            k: v
            for k, v in incident_data.items()
            if k not in settings.required_incident_fields and k != "flagged_false_positive"
        },
    }

    severity, recommended_action = await llm.suggest_severity_and_action(report_dict)
    report_dict["severity"] = severity
    report_dict["recommended_action"] = recommended_action

    report = IncidentReport(**report_dict)
    summary = await llm.generate_report_narrative(report_dict)
    return report, summary
