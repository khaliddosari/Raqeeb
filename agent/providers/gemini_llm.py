"""Google Gemini implementation of LLMProvider/VoiceSession, using the `google-genai`
SDK's Live API for realtime, duplex voice conversations.

Gemini here only ever: (1) talks to the human on the other end of the audio, (2) calls
tools to report structured data it heard, (3) drafts narrative text for the report. It
never sees or touches the raw YOLO detection tensors, and the tool schemas below never
expose a way to set detected_class/confidence -- those are injected read-only into the
system prompt by the caller and simply aren't tools Gemini can invoke.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agent.config import settings
from agent.providers.base import LLMProvider, ToolSpec, VoiceEvent, VoiceSession

_PCM_INPUT_MIME = "audio/pcm;rate=16000"


def _client():
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


class GeminiVoiceSession(VoiceSession):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[VoiceEvent] = asyncio.Queue()
        self._session_cm = None
        self._session = None
        self._pump_task: asyncio.Task | None = None

    async def start(self, system_instruction: str, tools: list[ToolSpec], language_code: str | None = None) -> None:
        from google.genai import types

        function_declarations = [
            {"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools
        ]
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=system_instruction)]),
            tools=[{"function_declarations": function_declarations}] if function_declarations else None,
            speech_config=types.SpeechConfig(language_code=language_code) if language_code else None,
        )
        self._session_cm = _client().aio.live.connect(model=settings.gemini_live_model, config=config)
        self._session = await self._session_cm.__aenter__()
        self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        assert self._session is not None
        try:
            print("[DEBUG gemini] live session connected, waiting for responses")
            async for response in self._session.receive():
                go_away = getattr(response, "go_away", None)
                if go_away:
                    print(f"[DEBUG gemini] go_away received, time_left={getattr(go_away, 'time_left', None)}")
                if getattr(response, "data", None):
                    await self._queue.put(VoiceEvent(type="audio", audio=response.data))
                text = getattr(response, "text", None)
                if text:
                    await self._queue.put(VoiceEvent(type="transcript", text=text))
                tool_call = getattr(response, "tool_call", None)
                if tool_call:
                    for fc in tool_call.function_calls:
                        await self._queue.put(
                            VoiceEvent(
                                type="tool_call",
                                tool_name=fc.name,
                                tool_args=dict(fc.args or {}),
                                tool_call_id=fc.id,
                            )
                        )
                if getattr(response, "server_content", None) and getattr(
                    response.server_content, "turn_complete", False
                ):
                    await self._queue.put(VoiceEvent(type="turn_complete"))
            print("[DEBUG gemini] receive() generator ended normally")
            await self._queue.put(VoiceEvent(type="closed", text="receive() ended"))
        except Exception as exc:  # connection dropped/closed mid-stream
            print(f"[DEBUG gemini] _pump raised: {exc!r}")
            await self._queue.put(VoiceEvent(type="closed", text=str(exc)))

    async def send_audio_chunk(self, pcm16_bytes: bytes) -> None:
        from google.genai import types

        assert self._session is not None
        await self._session.send_realtime_input(audio=types.Blob(data=pcm16_bytes, mime_type=_PCM_INPUT_MIME))

    async def send_text(self, text: str) -> None:
        from google.genai import types

        assert self._session is not None
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=text)]), turn_complete=True
        )

    async def receive_events(self) -> AsyncIterator[VoiceEvent]:
        while True:
            event = await self._queue.get()
            yield event
            if event.type == "closed":
                return

    async def send_tool_response(self, tool_name: str, response: dict[str, Any], tool_call_id: str | None = None) -> None:
        from google.genai import types

        assert self._session is not None
        await self._session.send_tool_response(
            function_responses=[types.FunctionResponse(id=tool_call_id, name=tool_name, response=response)]
        )

    async def close(self) -> None:
        if self._pump_task:
            self._pump_task.cancel()
        if self._session_cm is not None:
            await self._session_cm.__aexit__(None, None, None)


class GeminiLLMProvider(LLMProvider):
    async def generate_report_narrative(self, report_data: dict[str, Any]) -> str:
        client = _client()
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
        response = await asyncio.to_thread(
            client.models.generate_content, model=settings.gemini_text_model, contents=prompt
        )
        return response.text.strip()

    async def suggest_severity_and_action(self, report_data: dict[str, Any]) -> tuple[str, str]:
        client = _client()
        prompt = (
            "Given this security screening incident JSON, respond with ONLY a JSON object "
            '{"severity": "low|medium|high|critical", "recommended_action": "<one sentence, in Arabic>"}. '
            "The severity value itself must stay one of those exact English words (it drives "
            "internal logic/styling) -- only recommended_action should be in Arabic. "
            "Base the severity on the detected item and notes only -- never change or "
            "second-guess the verification_status field.\n\n"
            f"{json.dumps(report_data, default=str)}"
        )
        response = await asyncio.to_thread(
            client.models.generate_content, model=settings.gemini_text_model, contents=prompt
        )
        parsed = json.loads(response.text.strip().strip("`").removeprefix("json").strip())
        return parsed["severity"], parsed["recommended_action"]

    def create_voice_session(self) -> VoiceSession:
        return GeminiVoiceSession()
