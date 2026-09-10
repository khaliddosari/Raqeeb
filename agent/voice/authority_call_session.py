"""Drives the outbound authority phone call: bridges Twilio's Media Stream WebSocket
(raw mu-law audio frames, Twilio's own JSON framing) to a Gemini Live voice session.
Twilio only ever carries audio bytes here -- all conversational logic (what to say,
when to ask for confirmation, interpreting the answer) is Gemini's."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from fastapi import WebSocket

from agent.audio_utils import pcm16_24k_to_twilio_mulaw, twilio_mulaw_to_pcm16
from agent.providers.base import ToolSpec, VoiceEvent, VoiceSession
from agent.providers.factory import get_llm_provider

RECORD_DISPATCH_CONFIRMATION_TOOL = ToolSpec(
    name="record_dispatch_confirmation",
    description="Call once the authority has responded to the dispatch request, with their decision.",
    parameters={
        "type": "object",
        "properties": {
            "confirmed": {"type": "boolean", "description": "True if they agreed to dispatch a team."},
            "statement": {"type": "string", "description": "A short paraphrase of what they said."},
        },
        "required": ["confirmed", "statement"],
    },
)


class AuthorityCallSession:
    def __init__(self, websocket: WebSocket, *, incident_id: str, report_summary: str, report: dict[str, Any]) -> None:
        self.websocket = websocket
        self.incident_id = incident_id
        self.report_summary = report_summary
        self.report = report
        self.stream_sid: str | None = None
        self.transcript: list[dict[str, str]] = []
        self._result: dict[str, Any] | None = None
        self._finished = asyncio.Event()

    def _system_instruction(self) -> str:
        r = self.report
        return (
            "You are Raqeeb, calling on behalf of airport security. This is a phone call to "
            "an external authority -- speak clearly and professionally, like a real dispatch "
            "call, not a chatbot. In this order, tell them: "
            "(1) this is an automated security incident notification; "
            f"(2) the incident location: {r.get('location')}; "
            f"(3) the detected prohibited item: {r.get('detected_item')}; "
            "(4) that the detection was physically verified by an employee, not just an automated system; "
            f"(5) the employee's name: {r.get('employee', {}).get('name')}; "
            f"(6) the incident severity: {r.get('severity')}; "
            f"(7) the incident ID: {self.incident_id}; "
            "(8) confirm that the complete incident report has already been submitted to their system. "
            "Then explicitly request that they dispatch the appropriate team to the location and "
            "complete required procedures, and ask them to confirm. As soon as they give a clear "
            "yes/no answer, call record_dispatch_confirmation with their decision and a short "
            "paraphrase, then politely close the call. "
            f"Additional context/summary: {self.report_summary}"
        )

    async def run(self) -> dict[str, Any]:
        llm = get_llm_provider()
        session = llm.create_voice_session()
        await session.start(self._system_instruction(), [RECORD_DISPATCH_CONFIRMATION_TOOL])

        recv_task = asyncio.create_task(self._pump_from_twilio(session))
        try:
            async for event in session.receive_events():
                await self._handle_event(session, event)
                if self._finished.is_set() or event.type == "closed":
                    break
        finally:
            recv_task.cancel()
            await session.close()

        return self._result or {"dispatch_confirmed": False, "authority_statement": "", "raw_transcript": self.transcript}

    async def _pump_from_twilio(self, session: VoiceSession) -> None:
        try:
            while True:
                raw = await self.websocket.receive_text()
                message = json.loads(raw)
                event = message.get("event")
                if event == "start":
                    self.stream_sid = message["start"]["streamSid"]
                elif event == "media":
                    mulaw_bytes = base64.b64decode(message["media"]["payload"])
                    await session.send_audio_chunk(twilio_mulaw_to_pcm16(mulaw_bytes))
                elif event == "stop":
                    return
        except Exception:
            return

    async def _send_audio_to_twilio(self, pcm16_24k: bytes) -> None:
        if not self.stream_sid:
            return
        mulaw = pcm16_24k_to_twilio_mulaw(pcm16_24k)
        await self.websocket.send_text(
            json.dumps({"event": "media", "streamSid": self.stream_sid, "media": {"payload": base64.b64encode(mulaw).decode()}})
        )

    async def _handle_event(self, session: VoiceSession, event: VoiceEvent) -> None:
        if event.type == "audio" and event.audio:
            await self._send_audio_to_twilio(event.audio)
        elif event.type == "transcript" and event.text:
            self.transcript.append({"role": "assistant", "text": event.text})
        elif event.type == "tool_call" and event.tool_name == "record_dispatch_confirmation":
            confirmed = bool(event.tool_args.get("confirmed"))
            statement = str(event.tool_args.get("statement", ""))
            self.transcript.append({"role": "authority", "text": statement})
            self._result = {
                "dispatch_confirmed": confirmed,
                "authority_statement": statement,
                "raw_transcript": self.transcript,
            }
            await session.send_tool_response(event.tool_name, {"acknowledged": True}, event.tool_call_id)
            self._finished.set()
