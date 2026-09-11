"""Drives the authority call when it's bridged via OpenAI's SIP connector instead of
our own Media Stream WebSocket: Twilio dials sip.api.openai.com directly (see
TwilioTelephonyProvider.build_stream_twiml), so audio never touches our server at all.
We only accept the call over REST (agent/routes/openai_routes.py calls accept_call
here on the realtime.call.incoming webhook) and attach a lightweight WebSocket purely
to drive tool-calling and business logic -- mirroring AuthorityCallSession's behavior
for the audio-bridged (Gemini) path, but with no audio relay in this file at all."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from agent.config import settings
from agent.graph.runner import resume_incident
from agent.providers.openai_llm import function_tools, telephony_audio_config
from agent.voice.authority_prompts import RECORD_DISPATCH_CONFIRMATION_TOOL, build_dispatch_instructions

_ACCEPT_URL = "https://api.openai.com/v1/realtime/calls/{call_id}/accept"
_HANGUP_URL = "https://api.openai.com/v1/realtime/calls/{call_id}/hangup"
_REALTIME_URL = "wss://api.openai.com/v1/realtime"
_HANGUP_SAFETY_NET_SECONDS = 45
# The call ending doesn't reliably close this attached websocket on its own (seen in
# testing: the call completes on Twilio's side but our `async for` here just keeps
# waiting with no close frame and no further events), which would otherwise leave the
# incident's graph thread stuck at this interrupt forever -- so bound the whole
# observation by a ceiling no real dispatch call should need.
_MAX_CALL_SECONDS = 180


async def accept_call(call_id: str, incident_id: str, report: dict[str, Any]) -> None:
    instructions = build_dispatch_instructions(incident_id, report)
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            _ACCEPT_URL.format(call_id=call_id),
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "type": "realtime",
                "model": settings.openai_realtime_model,
                "instructions": instructions,
                "audio": telephony_audio_config(),
                "tools": function_tools([RECORD_DISPATCH_CONFIRMATION_TOOL]),
            },
        )
        response.raise_for_status()


async def observe_and_drive(call_id: str, incident_id: str) -> None:
    """Attaches to the already-accepted call to relay tool calls into the incident
    graph. Runs until the call ends (either party hangs up) or the safety net fires."""
    import websockets

    result: dict[str, Any] = {"dispatch_confirmed": False, "authority_statement": "", "raw_transcript": []}
    transcript: list[dict[str, str]] = []
    url = f"{_REALTIME_URL}?call_id={call_id}"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    safety_net_task: asyncio.Task | None = None

    async def _consume(ws) -> None:
        nonlocal safety_net_task
        async for raw in ws:
            message = json.loads(raw)
            msg_type = message.get("type")
            if msg_type == "response.output_audio_transcript.delta":
                print(f"[DEBUG sip {incident_id}] transcript: {message.get('delta')!r}")
            elif msg_type == "conversation.item.input_audio_transcription.completed":
                print(f"[DEBUG sip {incident_id}] heard from caller: {message.get('transcript')!r}")
            elif msg_type == "response.function_call_arguments.done":
                if message.get("name") != RECORD_DISPATCH_CONFIRMATION_TOOL.name:
                    continue
                args = json.loads(message["arguments"]) if message.get("arguments") else {}
                confirmed = bool(args.get("confirmed"))
                statement = str(args.get("statement", ""))
                transcript.append({"role": "authority", "text": statement})
                result["dispatch_confirmed"] = confirmed
                result["authority_statement"] = statement
                result["raw_transcript"] = transcript
                await ws.send(
                    json.dumps(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": message["call_id"],
                                "output": json.dumps({"acknowledged": True}),
                            },
                        }
                    )
                )
                await ws.send(json.dumps({"type": "response.create"}))
                # Don't hang up ourselves -- let the *other party* end the call, same as
                # AuthorityCallSession. This timer is only a safety net; cancelled below
                # once this function returns so it doesn't outlive the call it belongs to.
                safety_net_task = asyncio.create_task(_hangup_safety_net(call_id))
            elif msg_type == "error":
                print(f"[DEBUG sip {incident_id}] error event: {message.get('error')}")

    try:
        async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
            # This is an outbound call -- Raqeeb should speak first rather than wait for
            # the other side to talk first, which would never come. (Empirically the
            # SIP-accepted session has spoken first without this too, but that's an
            # undocumented default -- match the explicit trigger the direct-WebSocket
            # path (OpenAIVoiceSession.start) uses, rather than depend on it.)
            await ws.send(json.dumps({"type": "response.create"}))
            await asyncio.wait_for(_consume(ws), timeout=_MAX_CALL_SECONDS)
    except Exception as exc:  # connection closed, or _MAX_CALL_SECONDS elapsed -- either way, done
        print(f"[DEBUG sip {incident_id}] observe_and_drive ended: {exc!r}")
    finally:
        if safety_net_task is not None:
            safety_net_task.cancel()

    await resume_incident(incident_id, result)


async def _hangup_safety_net(call_id: str) -> None:
    await asyncio.sleep(_HANGUP_SAFETY_NET_SECONDS)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                _HANGUP_URL.format(call_id=call_id),
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
        except Exception:
            pass
