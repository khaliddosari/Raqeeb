"""OpenAI implementation of LLMProvider/VoiceSession, using the GA Realtime API
(https://developers.openai.com/api/docs/guides/realtime) over a raw WebSocket --
there's no `openai` pip package dependency here, deliberately: the official SDK's
websocket transport pulls in an aiohttp version newer than the one twilio/other deps
in this project pin, and the wire protocol is simple enough to speak directly.

Session audio is configured as audio/pcmu (G.711 mu-law @ 8kHz) both ways -- the same
encoding Twilio's Media Streams use natively, so this provider sets
wants_raw_telephony_audio and callers forward Twilio's bytes unconverted instead of
resampling like the Gemini provider needs.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from agent.config import settings
from agent.providers.base import LLMProvider, ToolSpec, VoiceEvent, VoiceSession

_REALTIME_URL = "wss://api.openai.com/v1/realtime"
_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def telephony_audio_config() -> dict[str, Any]:
    """The audio/pcmu + turn-detection/noise/transcription config shared by both ways
    a phone call reaches the Realtime API: attached over our own WebSocket
    (OpenAIVoiceSession.start, below) or accepted via REST for the SIP-bridged path
    (agent/voice/sip_authority_call.py's accept_call). Kept in one place so tuning
    changes (VAD sensitivity, transcription model, etc.) can't drift between the two."""
    return {
        "input": {
            "format": {"type": "audio/pcmu"},
            # Semantic VAD judges actual turn-completion with a model, rather
            # than pure amplitude thresholding -- less prone to false-triggering
            # on phone-line noise than server_vad, which was firing on silence
            # and getting Whisper-hallucinated "transcripts" of it.
            "turn_detection": {
                "type": "semantic_vad",
                "eagerness": "high",
                "create_response": True,
                "interrupt_response": True,
            },
            # Phone audio held close to the mouth -- near_field, not
            # far_field (that's for laptop/conference-room mics) --
            # filters some of the line noise before VAD/the model see it.
            "noise_reduction": {"type": "near_field"},
            # Debug visibility into what the model actually heard. This is a
            # separate ASR pass for our own logs only -- gpt-realtime itself
            # always understands the raw audio directly, this doesn't feed it.
            "transcription": {"model": "gpt-4o-transcribe", "language": "ar"},
        },
        "output": {
            "format": {"type": "audio/pcmu"},
            "voice": settings.openai_voice,
        },
    }


def browser_audio_config() -> dict[str, Any]:
    """The same conversation held in a browser instead of over a phone (see
    agent/routes/browser_call.py). No format is named: WebRTC negotiates Opus at full
    bandwidth, so the 8kHz mu-law of the telephony path would only throw quality away. The
    microphone is a laptop's, across a room rather than against a mouth, so noise reduction
    is far_field."""
    return {
        "input": {
            "turn_detection": {
                "type": "semantic_vad",
                "eagerness": "high",
                "create_response": True,
                "interrupt_response": True,
            },
            "noise_reduction": {"type": "far_field"},
            "transcription": {"model": "gpt-4o-transcribe", "language": "ar"},
        },
        "output": {"voice": settings.openai_voice},
    }


def function_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [{"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]


class OpenAIVoiceSession(VoiceSession):
    wants_raw_telephony_audio = True

    def __init__(self) -> None:
        self._ws = None
        self._queue: asyncio.Queue[VoiceEvent] = asyncio.Queue()
        self._pump_task: asyncio.Task | None = None

    async def start(self, system_instruction: str, tools: list[ToolSpec], language_code: str | None = None) -> None:
        import websockets

        url = f"{_REALTIME_URL}?model={settings.openai_realtime_model}"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        self._ws = await websockets.connect(url, additional_headers=headers, max_size=None)

        await self._ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "model": settings.openai_realtime_model,
                        "instructions": system_instruction,
                        "audio": telephony_audio_config(),
                        "tools": function_tools(tools) or None,
                    },
                }
            )
        )
        # This is an outbound call -- Raqeeb should speak first rather than wait for
        # server_vad to detect speech from the other side, which would never come.
        await self._ws.send(json.dumps({"type": "response.create"}))
        self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                message = json.loads(raw)
                msg_type = message.get("type")
                if msg_type == "response.output_audio.delta":
                    await self._queue.put(VoiceEvent(type="audio", audio=base64.b64decode(message["delta"])))
                elif msg_type == "response.output_audio_transcript.delta":
                    await self._queue.put(VoiceEvent(type="transcript", text=message["delta"]))
                elif msg_type == "response.function_call_arguments.done":
                    await self._queue.put(
                        VoiceEvent(
                            type="tool_call",
                            tool_name=message["name"],
                            tool_args=json.loads(message["arguments"]) if message.get("arguments") else {},
                            tool_call_id=message["call_id"],
                        )
                    )
                elif msg_type == "response.done":
                    await self._queue.put(VoiceEvent(type="turn_complete"))
                elif msg_type == "conversation.item.input_audio_transcription.completed":
                    print(f"[DEBUG openai] heard from caller: {message.get('transcript')!r}")
                elif msg_type == "input_audio_buffer.speech_started":
                    print("[DEBUG openai] speech_started (VAD detected the caller talking)")
                    # With interrupt_response=True, the server cancels any in-progress
                    # response right now -- but any of that response's audio we already
                    # forwarded to Twilio is still sitting in Twilio's own playback
                    # buffer. Tell the caller to flush it, or the old response keeps
                    # audibly playing for seconds after the model has already moved on.
                    await self._queue.put(VoiceEvent(type="interrupted"))
                elif msg_type == "input_audio_buffer.speech_stopped":
                    print("[DEBUG openai] speech_stopped")
                elif msg_type == "error":
                    print(f"[DEBUG openai] error event: {message.get('error')}")
                    await self._queue.put(VoiceEvent(type="closed", text=f"error event: {message.get('error')}"))
                    return
        except Exception as exc:  # connection dropped/closed mid-stream
            await self._queue.put(VoiceEvent(type="closed", text=str(exc)))
            return
        await self._queue.put(VoiceEvent(type="closed", text="connection ended"))

    async def send_audio_chunk(self, audio_bytes: bytes) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(audio_bytes).decode()})
        )

    async def send_text(self, text: str) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
                }
            )
        )
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def receive_events(self) -> AsyncIterator[VoiceEvent]:
        while True:
            event = await self._queue.get()
            yield event
            if event.type == "closed":
                return

    async def send_tool_response(self, tool_name: str, response: dict[str, Any], tool_call_id: str | None = None) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": tool_call_id,
                        "output": json.dumps(response),
                    },
                }
            )
        )
        # Unlike a user's spoken turn (auto-triggered by server VAD), a tool result
        # doesn't itself prompt the model to continue -- ask it to explicitly.
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def close(self) -> None:
        if self._pump_task:
            self._pump_task.cancel()
        if self._ws is not None:
            await self._ws.close()


class OpenAILLMProvider(LLMProvider):
    async def generate_report_narrative(self, report_data: dict[str, Any]) -> str:
        prompt = (
            "Write a detailed, professional security screening incident report from this JSON, "
            "IN ARABIC (Modern Standard Arabic, formal report register). This is the full written "
            "report record -- be thorough, not brief. Structure it as several short paragraphs "
            "under clear headers (use Arabic headers, e.g. as bold-style lines): "
            "(1) a summary of what happened; "
            "(2) detection and verification details (how it was found, the detector's confidence, "
            "and how the employee physically confirmed it); "
            "(3) suspect and reporting details (who was involved, who reported it, any notes), "
            "including the operational context in the `scenario` object: the event, the checkpoint, "
            "the conditions when it was found, what staff have already done, and how responders "
            "should approach; "
            "(4) a risk assessment explaining WHY this item/situation warrants its severity level "
            "(reason about it, don't just state the level); "
            "(5) recommended next steps for the responding team, beyond the one-line action. "
            "Do not invent facts not present in the data, and do not alter the detected item or "
            "confidence value -- where a section would need information that isn't in the data, "
            "say so plainly rather than making it up.\n\n"
            f"{json.dumps(report_data, default=str)}"
        )
        content = await self._chat_completion(prompt)
        return content.strip()

    async def suggest_severity_and_action(self, report_data: dict[str, Any]) -> tuple[str, str]:
        prompt = (
            "Given this security screening incident JSON, respond with ONLY a JSON object "
            '{"severity": "low|medium|high|critical", "recommended_action": "<one sentence, in Arabic>"}. '
            "The severity value itself must stay one of those exact English words (it drives "
            "internal logic/styling) -- only recommended_action should be in Arabic. "
            "Base the severity on the detected item and notes only -- never change or "
            "second-guess the verification_status field.\n\n"
            f"{json.dumps(report_data, default=str)}"
        )
        content = await self._chat_completion(prompt)
        parsed = json.loads(content.strip().strip("`").removeprefix("json").strip())
        return parsed["severity"], parsed["recommended_action"]

    async def _chat_completion(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                _CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_text_model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def create_voice_session(self) -> VoiceSession:
        return OpenAIVoiceSession()
