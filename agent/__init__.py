"""Raqeeb voice-agent application package.

Layers:
    yolo_detector.py   -- detection only (never changed by anything downstream)
    graph/             -- LangGraph workflow orchestration + state
    providers/          -- pluggable LLM (Gemini/mock) and telephony (Twilio/mock) backends
    voice/              -- realtime voice sessions (employee <-> Gemini, authority <-> Gemini)
    routes/             -- FastAPI HTTP/WebSocket endpoints
"""
