"""Drives the outbound authority phone call: bridges Twilio's Media Stream WebSocket
(raw mu-law audio frames, Twilio's own JSON framing) to a realtime voice session
(Gemini Live or OpenAI Realtime, whichever LLM_PROVIDER selects). Twilio only ever
carries audio bytes here -- all conversational logic (what to say, when to ask for
confirmation, interpreting the answer) is the model's."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from fastapi import WebSocket

from agent import monitor
from agent.audio_utils import TwilioAudioBridge
from agent.providers.base import VoiceEvent, VoiceSession
from agent.providers.factory import get_llm_provider
from agent.voice.authority_prompts import RECORD_DISPATCH_CONFIRMATION_TOOL, build_dispatch_instructions


class AuthorityCallSession:
    def __init__(self, websocket: WebSocket, *, incident_id: str, report: dict[str, Any]) -> None:
        self.websocket = websocket
        self.incident_id = incident_id
        self.report = report
        self.stream_sid: str | None = None
        self.transcript: list[dict[str, str]] = []
        self._result: dict[str, Any] | None = None
        self._finished = asyncio.Event()
        self._audio = TwilioAudioBridge()
        self._hangup_safety_net_task: asyncio.Task | None = None

    def _system_instruction(self) -> str:
        return build_dispatch_instructions(self.incident_id, self.report)

    async def run(self) -> dict[str, Any]:
        llm = get_llm_provider()
        session = llm.create_voice_session()
        # Native-audio Gemini models reject an explicit speech_config.language_code --
        # they're multilingual by default and pick up the target language from the
        # system instruction itself instead. (OpenAI's provider ignores this too --
        # it has no separate language config, same reasoning.)
        await session.start(self._system_instruction(), [RECORD_DISPATCH_CONFIRMATION_TOOL])

        recv_task = asyncio.create_task(self._pump_from_twilio(session))
        events_task = asyncio.create_task(self._consume_events(session))
        finished_task = asyncio.create_task(self._finished.wait())
        try:
            # Race the event-consuming loop against the call-ended signal -- if Twilio
            # hangs up before the model ever calls record_dispatch_confirmation,
            # events_task would otherwise block forever waiting on a Gemini event that
            # will never arrive.
            await asyncio.wait({events_task, finished_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            recv_task.cancel()
            events_task.cancel()
            finished_task.cancel()
            if self._hangup_safety_net_task is not None:
                self._hangup_safety_net_task.cancel()
            await session.close()

        return self._result or {"dispatch_confirmed": False, "authority_statement": "", "raw_transcript": self.transcript}

    async def _consume_events(self, session: VoiceSession) -> None:
        async for event in session.receive_events():
            await self._handle_event(session, event)
            if self._finished.is_set() or event.type == "closed":
                return

    async def _pump_from_twilio(self, session: VoiceSession) -> None:
        media_chunks = 0
        try:
            while True:
                raw = await self.websocket.receive_text()
                message = json.loads(raw)
                event = message.get("event")
                if event == "start":
                    self.stream_sid = message["start"]["streamSid"]
                    print(f"[DEBUG {self.incident_id}] twilio stream started, stream_sid={self.stream_sid}")
                elif event == "media":
                    mulaw_bytes = base64.b64decode(message["media"]["payload"])
                    if session.wants_raw_telephony_audio:
                        await session.send_audio_chunk(mulaw_bytes)
                    else:
                        await session.send_audio_chunk(self._audio.twilio_mulaw_to_pcm16(mulaw_bytes))
                    media_chunks += 1
                    if media_chunks % 100 == 0:
                        print(f"[DEBUG {self.incident_id}] forwarded {media_chunks} media chunks to the model")
                elif event == "stop":
                    print(f"[DEBUG {self.incident_id}] twilio stream stopped after {media_chunks} chunks")
                    return
        except Exception as exc:
            print(f"[DEBUG {self.incident_id}] _pump_from_twilio raised: {exc!r}")
            return
        finally:
            # The call ended (hangup/disconnect) before the model ever called
            # record_dispatch_confirmation -- without this, the run() loop below keeps
            # waiting on Gemini events that will never come, and the incident's graph
            # thread stays stuck at this interrupt forever.
            self._finished.set()

    async def _send_audio_to_twilio(self, audio_bytes: bytes, *, raw_telephony_audio: bool) -> None:
        if not self.stream_sid:
            return
        mulaw = audio_bytes if raw_telephony_audio else self._audio.pcm16_24k_to_twilio_mulaw(audio_bytes)
        await self.websocket.send_text(
            json.dumps({"event": "media", "streamSid": self.stream_sid, "media": {"payload": base64.b64encode(mulaw).decode()}})
        )

    async def _clear_twilio_playback_buffer(self) -> None:
        if not self.stream_sid:
            return
        print(f"[DEBUG {self.incident_id}] barge-in: clearing Twilio's queued playback")
        await self.websocket.send_text(json.dumps({"event": "clear", "streamSid": self.stream_sid}))

    async def _handle_event(self, session: VoiceSession, event: VoiceEvent) -> None:
        if event.type == "audio" and event.audio:
            print(f"[DEBUG {self.incident_id}] got {len(event.audio)} bytes of audio from the model")
            await self._send_audio_to_twilio(event.audio, raw_telephony_audio=session.wants_raw_telephony_audio)
        elif event.type == "interrupted":
            await self._clear_twilio_playback_buffer()
        elif event.type == "transcript" and event.text:
            print(f"[DEBUG {self.incident_id}] transcript: {event.text!r}")
            self.transcript.append({"role": "assistant", "text": event.text})
            monitor.publish_transcript(self.incident_id, "assistant", event.text)
        elif event.type == "closed":
            print(f"[DEBUG {self.incident_id}] voice session closed: {event.text!r}")
        elif event.type == "tool_call" and event.tool_name == "record_dispatch_confirmation":
            confirmed = bool(event.tool_args.get("confirmed"))
            statement = str(event.tool_args.get("statement", ""))
            self.transcript.append({"role": "authority", "text": statement})
            monitor.publish_transcript(self.incident_id, "authority", statement)
            monitor.publish(
                self.incident_id,
                {"type": "dispatch", "confirmed": confirmed, "statement": statement},
            )
            self._result = {
                "dispatch_confirmed": confirmed,
                "authority_statement": statement,
                "raw_transcript": self.transcript,
            }
            await session.send_tool_response(event.tool_name, {"acknowledged": True}, event.tool_call_id)
            # Don't hang up ourselves the instant we have a confirmation -- let the
            # model finish its closing remark and let the *other party* end the call
            # (handled by _pump_from_twilio's finally, once Twilio reports the stream
            # stopped). This timer is only a safety net in case they never hang up.
            self._hangup_safety_net_task = asyncio.create_task(self._hangup_safety_net())

    async def _hangup_safety_net(self) -> None:
        await asyncio.sleep(45)
        self._finished.set()
