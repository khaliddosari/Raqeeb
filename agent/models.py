from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.db import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Incident(Base):
    """One row per detection-to-resolution incident. `detection_class` and
    `detection_confidence` are written exactly once (by the yolo_detection node)
    and never modified afterwards by any downstream component."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="pending_detection")

    # --- YOLO output (immutable after creation) ---
    detection_class: Mapped[str] = mapped_column(String)
    detection_confidence: Mapped[float] = mapped_column(Float)
    image_path: Mapped[str] = mapped_column(String)

    # --- Employee verification (source of truth) ---
    verification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_channel: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_name: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Collected incident info / report ---
    incident_data: Mapped[dict] = mapped_column(JSON, default=dict)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_summary: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Authority routing / call ---
    authority_name: Mapped[str | None] = mapped_column(String, nullable=True)
    authority_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    call_sid: Mapped[str | None] = mapped_column(String, nullable=True)
    authority_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    stage: Mapped[str] = mapped_column(String)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)
