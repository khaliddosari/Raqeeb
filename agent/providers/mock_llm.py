"""Deterministic mock provider. Same interface as the Gemini provider, so the whole
LangGraph workflow can be exercised end-to-end with LLM_PROVIDER=mock and no API key.

Voice turns are driven via send_text() using a tiny convention instead of real audio/NLU:
    "TOOL:<tool_name>:<json_args>"  -> emits a tool_call event immediately
    anything else                   -> emitted back as a transcript event (echo)
This keeps the mock exercising the exact same VoiceSession contract the real Gemini
Live session uses, so graph/route code never needs to know which one it's talking to.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agent.providers.base import LLMProvider, ToolSpec, VoiceEvent, VoiceSession


class MockVoiceSession(VoiceSession):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[VoiceEvent] = asyncio.Queue()
        self._closed = False

    async def start(self, system_instruction: str, tools: list[ToolSpec]) -> None:
        self._tools = {t.name for t in tools}

    async def send_audio_chunk(self, pcm16_bytes: bytes) -> None:
        # No real ASR in mock mode; audio is accepted but ignored.
        return

    async def send_text(self, text: str) -> None:
        if text.startswith("TOOL:"):
            _, name, args_json = text.split(":", 2)
            await self._queue.put(VoiceEvent(type="tool_call", tool_name=name, tool_args=json.loads(args_json)))
        else:
            await self._queue.put(VoiceEvent(type="transcript", text=text))
        await self._queue.put(VoiceEvent(type="turn_complete"))

    async def receive_events(self) -> AsyncIterator[VoiceEvent]:
        while not self._closed:
            event = await self._queue.get()
            yield event

    async def send_tool_response(self, tool_name: str, response: dict[str, Any], tool_call_id: str | None = None) -> None:
        # Mock mode has no live model turn to unblock; nothing to do.
        return

    async def close(self) -> None:
        self._closed = True
        await self._queue.put(VoiceEvent(type="closed"))


class MockLLMProvider(LLMProvider):
    async def generate_report_narrative(self, report_data: dict[str, Any]) -> str:
        suspect = report_data.get("suspect", {})
        return (
            f"Security incident {report_data['incident_id']}: a {report_data['detected_item']} "
            f"was detected at {report_data['location']} with {report_data['yolo_confidence']:.0%} "
            f"confidence and physically verified by employee {report_data['employee'].get('name')}. "
            f"Suspect: {suspect.get('name', 'unknown')}. Notes: {report_data.get('inspection_notes', 'n/a')}."
        )

    async def suggest_severity_and_action(self, report_data: dict[str, Any]) -> tuple[str, str]:
        high_risk = {"Gun", "Knife"}
        if report_data["detected_item"] in high_risk:
            return "high", "Immediate dispatch of armed response unit to location."
        return "medium", "Dispatch standard security team to location for inspection."

    def create_voice_session(self) -> VoiceSession:
        return MockVoiceSession()
