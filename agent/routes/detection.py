from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.auth import is_admin
from agent.config import settings
from agent.db import get_db
from agent.authority_mapping import get_authority_for_class
from agent.employees import BY_KEY, EMPLOYEES, call_numbers
from agent.graph.runner import start_incident
from agent.intake import validate_location
from agent.models import Incident
from agent.report import new_incident_id
from agent.yolo_detector import NoDetectionError, YoloDetector

router = APIRouter(prefix="/api", tags=["detection"])


@router.post("/detect")
async def detect(
    image: UploadFile,
    employee_key: str = Form(""),
    location: str = Form(""),
    authorization: str | None = Header(default=None),
):
    """YOLO detection entrypoint. Saves the frame, runs the graph up to (and including)
    the employee_verification interrupt, and returns the detection for the dashboard.

    employee_key names one of agent/employees.py; their name and staff number go on the report.
    No phone number is accepted from the caller: signed in as the team, the dispatch call rings
    the mobile configured for that employee in ADMIN_CALL_NUMBERS, and otherwise the incident
    holds its dispatch conversation in the visitor's own browser. location picks one of the fixed
    checkpoints; without it the configured default is used."""
    employee = BY_KEY.get(employee_key.strip()) or (EMPLOYEES[0] if not employee_key.strip() else None)
    if employee is None:
        raise HTTPException(status_code=422, detail="Unknown employee.")
    try:
        checkpoint = validate_location(location) if location else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    call_phone = call_numbers().get(employee.key) if is_admin(authorization) else None
    if is_admin(authorization) and not call_phone:
        raise HTTPException(
            status_code=422,
            detail=f"No number is configured for {employee.name_en} in ADMIN_CALL_NUMBERS. "
            "Add one, or sign out to hold the dispatch conversation in this browser instead.",
        )

    incident_id = new_incident_id()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(image.filename or "frame.jpg").suffix or ".jpg"
    image_path = upload_dir / f"{incident_id}{ext}"
    image_path.write_bytes(await image.read())

    try:
        result = await start_incident(
            incident_id,
            str(image_path),
            employee_name=employee.name_ar,
            employee_id=employee.badge,
            location=checkpoint,
            call_phone=call_phone,
            call_transport="phone" if call_phone else "browser",
        )
    except NoDetectionError:
        raise HTTPException(status_code=422, detail="No prohibited item detected in this frame.")

    annotated = YoloDetector.annotated_path_for(str(image_path))
    return {
        "incident_id": incident_id,
        "interrupt": result["interrupt"],
        "image_filename": image_path.name,
        "annotated_filename": annotated.name if annotated.exists() else None,
    }


@router.get("/incidents")
def list_incidents(db: Session = Depends(get_db)):
    incidents = db.execute(select(Incident).order_by(Incident.created_at.desc()).limit(100)).scalars().all()
    return [_serialize(i) for i in incidents]


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _serialize(incident)


def _mapped_authority(detection_class: str | None):
    if not detection_class:
        return None
    try:
        return get_authority_for_class(detection_class)
    except ValueError:
        return None


def _serialize(incident: Incident) -> dict:
    mapped = _mapped_authority(incident.detection_class)
    annotated = None
    if incident.image_path:
        candidate = YoloDetector.annotated_path_for(incident.image_path)
        if candidate.exists():
            annotated = candidate.name

    return {
        "id": incident.id,
        "status": incident.status,
        "detection_class": incident.detection_class,
        "detection_confidence": incident.detection_confidence,
        "image_filename": Path(incident.image_path).name if incident.image_path else None,
        "annotated_filename": annotated,
        "verification_status": incident.verification_status,
        "employee_name": incident.employee_name,
        "employee_id": incident.employee_id,
        "incident_data": incident.incident_data,
        "report": incident.report_json,
        "report_summary": incident.report_summary,
        "authority_name": incident.authority_name,
        # Which agency this class routes to, so the dashboard can show that agency's mark as
        # soon as the item is detected. Read from the mapping, which is the routing source of truth.
        "authority_agency": mapped.agency if mapped else None,
        "authority_name_ar": mapped.name_ar if mapped and incident.authority_name else None,
        # authority_phone is deliberately absent: this endpoint is public, and the number is a
        # real mobile. The dashboard never showed it, and the record still holds it.
        "call_sid": incident.call_sid,
        "authority_response": incident.authority_response,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }
