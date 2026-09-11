"""Centralized settings loaded from environment variables. Never hard-code credentials here."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM provider (Gemini is the default; set LLM_PROVIDER=openai to swap) ---
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-3.6-flash"
    gemini_live_model: str = "gemini-2.5-flash-native-audio-latest"

    # OpenAI's Realtime API (GA). Its audio/pcmu format is 8kHz mu-law -- the same
    # encoding Twilio's Media Streams already use, so no resampling is needed on this
    # path (see VoiceSession.wants_raw_telephony_audio).
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime"
    openai_voice: str = "marin"
    openai_text_model: str = "gpt-4o-mini"

    # SIP connector: Twilio dials sip.api.openai.com directly for the authority call
    # (see TwilioTelephonyProvider.build_stream_twiml), bypassing our own server for
    # audio entirely -- OpenAI notifies us of the call via this webhook instead.
    openai_project_id: str = ""
    openai_webhook_secret: str = ""

    # --- Telephony provider ---
    telephony_provider: str = "twilio"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # SignalWire's Compatibility API mirrors Twilio's -- an alternative telephony
    # backend, set TELEPHONY_PROVIDER=signalwire to use it.
    signalwire_project_id: str = ""
    signalwire_token: str = ""
    signalwire_space_url: str = ""
    signalwire_phone_number: str = ""

    # Public base URL this server is reachable at (needed so Twilio can call back into
    # our webhook / media-stream websocket). e.g. https://your-ngrok-domain.ngrok.io
    public_base_url: str = "http://localhost:8000"

    # --- Storage ---
    database_url: str = "sqlite:///./raqeeb.db"

    # --- YOLO ---
    yolo_weights_path: str = str(BASE_DIR / "best_yolov8s.pt")
    yolo_confidence_threshold: float = 0.25
    upload_dir: str = str(BASE_DIR / "uploads")

    # Fixed location of this scanning checkpoint. Stamped onto every incident at
    # detection time -- it is never asked for, by form or by voice.
    checkpoint_location: str = "Main Terminal - Checkpoint 1"

    # --- Authority routing config ---
    authority_mapping_path: str = str(BASE_DIR / "config" / "authority_mapping.yaml")

    # Required fields the report must have before it can be generated. Kept here (not
    # hard-coded in report.py) so ops can extend the checklist without a code change.
    # location/employee_name/employee_id are stamped in automatically at detection time
    # (see checkpoint_location above and start_incident() in graph/runner.py), so in
    # practice suspect_name and suspect_id_number are the only two ever actively asked
    # for -- whether by voice (agent/voice/employee_session.py) or the dashboard's quick
    # form (agent/routes/verification.py's /manual-info).
    required_incident_fields: tuple[str, ...] = (
        "location",
        "suspect_name",
        "suspect_id_number",
        "employee_name",
        "employee_id",
    )


settings = Settings()


def is_mock_llm() -> bool:
    return settings.llm_provider.lower() == "mock"


def is_mock_telephony() -> bool:
    return settings.telephony_provider.lower() == "mock"


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
