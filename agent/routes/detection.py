from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.config import settings
from agent.db import get_db
from agent.graph.runner import start_incident
from agent.models import Incident
from agent.report import new_incident_id
from agent.yolo_detector import NoDetectionError, YoloDetector

router = APIRouter(prefix="/api", tags=["detection"])


@router.post("/detect")
async def detect(image: UploadFile, employee_name: str = Form(...), employee_id: str = Form(...)):
    """YOLO detection entrypoint. Saves the frame, runs the graph up to (and including)
    the employee_verification interrupt, and returns the detection for the dashboard.
    employee_name/employee_id come from the on-duty employee's shift login on the
    dashboard -- the checkpoint's location is stamped in automatically from config."""
    incident_id = new_incident_id()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(image.filename or "frame.jpg").suffix or ".jpg"
    image_path = upload_dir / f"{incident_id}{ext}"
    image_path.write_bytes(await image.read())

    try:
        result = await start_incident(
            incident_id, str(image_path), employee_name=employee_name, employee_id=employee_id
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


def _serialize(incident: Incident) -> dict:
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
        "authority_phone": incident.authority_phone,
        "call_sid": incident.call_sid,
        "authority_response": incident.authority_response,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }
