"""Drives one employee <-> Gemini voice conversation over a browser WebSocket.

This is what runs while the graph is paused at the collect_incident_information
interrupt. It never touches verification_status by itself except via the explicit
flag_false_positive tool -- and even then it's relaying what the employee said, not
Gemini's own judgement (Gemini has no visibility into anything that would let it
infer a false positive on its own; the tool only fires on an explicit employee
statement in the transcript that its instructions tell it to listen for)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from agent.providers.base import ToolSpec, VoiceEvent, VoiceSession
from agent.providers.factory import get_llm_provider

RECORD_FIELD_TOOL = ToolSpec(
    name="record_field",
    description="Record one piece of incident information the employee just stated out loud.",
    parameters={
        "type": "object",
        "properties": {
            "field_name": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["field_name", "value"],
    },
)

FLAG_FALSE_POSITIVE_TOOL = ToolSpec(
    name="flag_false_positive",
    description="Call this ONLY if the employee explicitly says this detection was a false alarm/mistake.",
    parameters={"type": "object", "properties": {}},
)

FINISH_COLLECTION_TOOL = ToolSpec(
    name="finish_collection",
    description="Call once every required field is recorded and the employee has nothing more to add.",
    parameters={"type": "object", "properties": {}},
)


class EmployeeVoiceSession:
    def __init__(
        self,
        websocket: WebSocket,
        *,
        detection_class: str,
        detection_confidence: float,
        required_fields: list[str],
        already_collected: dict[str, Any],
    ) -> None:
        self.websocket = websocket
        self.detection_class = detection_class
        self.detection_confidence = detection_confidence
        self.required_fields = required_fields
        self.collected: dict[str, Any] = dict(already_collected)
        self.flagged_false_positive = False
        self._finished = asyncio.Event()

    def _missing(self) -> list[str]:
        return [f for f in self.required_fields if not self.collected.get(f)]

    def _system_instruction(self) -> str:
        return (
            "You are Raqeeb, a calm airport-security voice assistant. The employee has "
            "already PHYSICALLY VERIFIED a prohibited-item detection; your job now is only "
            "to collect incident details by conversation, never to re-judge the detection. "
            f"Detected item (read-only context, never restate as a question or change it): "
            f"{self.detection_class}, confidence {self.detection_confidence:.0%}. "
            f"Already collected: {self.collected}. Still needed: {self._missing()}. "
            "Ask for missing fields naturally, one or two at a time. Call record_field the "
            "moment the employee states a value for one of them. Capture any other relevant "
            "detail the employee volunteers with record_field too (pick a short field_name "
            "for it). If, and only if, the employee explicitly says this was a false alarm "
            "or a mistake, call flag_false_positive immediately and stop collecting. "
            "Once all required fields are recorded, briefly read the summary back to the "
            "employee for confirmation, then call finish_collection."
        )

    async def run(self) -> dict[str, Any]:
        llm = get_llm_provider()
        session = llm.create_voice_session()
        await session.start(
            self._system_instruction(), [RECORD_FIELD_TOOL, FLAG_FALSE_POSITIVE_TOOL, FINISH_COLLECTION_TOOL]
        )

        recv_task = asyncio.create_task(self._pump_from_websocket(session))
        try:
            async for event in session.receive_events():
                await self._handle_event(session, event)
                if self.flagged_false_positive or self._finished.is_set() or event.type == "closed":
                    break
        finally:
            recv_task.cancel()
            await session.close()

        return {"flagged_false_positive": self.flagged_false_positive, "fields": self.collected}

    async def _pump_from_websocket(self, session: VoiceSession) -> None:
        try:
            while True:
                message = await self.websocket.receive()
                if message.get("bytes") is not None:
                    await session.send_audio_chunk(message["bytes"])
                elif message.get("text") is not None:
                    await session.send_text(message["text"])
        except Exception:
            return

    async def _handle_event(self, session: VoiceSession, event: VoiceEvent) -> None:
        if event.type == "audio" and event.audio:
            await self.websocket.send_bytes(event.audio)
        elif event.type == "transcript" and event.text:
            await self.websocket.send_json({"type": "transcript", "text": event.text})
        elif event.type == "tool_call":
            await self._handle_tool_call(session, event)

    async def _handle_tool_call(self, session: VoiceSession, event: VoiceEvent) -> None:
        if event.tool_name == "record_field":
            field = event.tool_args.get("field_name")
            value = event.tool_args.get("value")
            if field and value:
                self.collected[field] = value
                await self.websocket.send_json({"type": "field_recorded", "field": field, "value": value})
            await session.send_tool_response(
                event.tool_name, {"recorded": field, "still_missing": self._missing()}, event.tool_call_id
            )
        elif event.tool_name == "flag_false_positive":
            self.flagged_false_positive = True
            await self.websocket.send_json({"type": "false_positive_flagged"})
            await session.send_tool_response(event.tool_name, {"acknowledged": True}, event.tool_call_id)
        elif event.tool_name == "finish_collection":
            missing = self._missing()
            if missing:
                await session.send_tool_response(
                    event.tool_name, {"error": "still_missing_fields", "missing": missing}, event.tool_call_id
                )
            else:
                self._finished.set()
                await session.send_tool_response(event.tool_name, {"acknowledged": True}, event.tool_call_id)
