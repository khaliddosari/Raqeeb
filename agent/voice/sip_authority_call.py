"""Drives the authority call when it's bridged via OpenAI's SIP connector instead of
our own Media Stream WebSocket: Twilio dials sip.api.openai.com directly (see
TwilioTelephonyProvider.build_stream_twiml), so audio never touches our server at all.
We only accept the call over REST (agent/routes/openai_routes.py calls accept_call
here on the realtime.call.incoming webhook) and attach a lightweight WebSocket purely
to drive tool-calling and business logic -- mirroring AuthorityCallSession's behavior
for the audio-bridged (Gemini) path, but with no audio relay in this file at all.

That same WebSocket carries both sides' words as text, which LiveTranscript streams to the
dashboard while the call is happening."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from agent import monitor
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

# Returned to the model when it records a decision before anyone on the line has said a word.
_NO_DECISION_HEARD = (
    "لم يُسجَّل شيء: لم يتكلّم أحد من الجهة بعد، فلا يوجد قرار. "
    "تأكّد أن من على الخط شخص من الجهة، وأكمل البلاغ، ولا تستدعِ الأداة إلا بعد أن تسمع قرارهم."
)


class LiveTranscript:
    """Both sides of the call as ordered lines, published to the dashboard as they are spoken.

    The Realtime API streams the agent's words while it speaks, and transcribes the other
    party separately, often finishing that after the agent has already started replying. So
    lines are keyed by conversation item and ordered by when each turn began, not by when its
    text arrived. Every update carries the line's whole text so far, which lets a dashboard
    that joins late or misses an event still converge on the right transcript. Updates for a
    growing line are throttled; the finished line always goes out."""

    THROTTLE_SECONDS = 0.15

    def __init__(self, incident_id: str, clock: Callable[[], float] = time.monotonic) -> None:
        self.incident_id = incident_id
        self._clock = clock
        self._lines: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._last_sent: dict[str, float] = {}

    def handle(self, message: dict[str, Any]) -> bool:
        """Consumes a Realtime event if it is part of the transcript; returns whether it was."""
        msg_type = message.get("type")
        if msg_type == "input_audio_buffer.committed":
            # the authority finished a turn; claim its place before its transcription arrives
            self._line(message["item_id"], "authority")
        elif msg_type == "response.output_item.added":
            item = message.get("item") or {}
            if item.get("type") != "message":
                return False
            self._line(item["id"], "assistant")
        elif msg_type == "conversation.item.input_audio_transcription.delta":
            self._append(message["item_id"], "authority", message.get("delta", ""))
        elif msg_type == "conversation.item.input_audio_transcription.completed":
            self._finish(message["item_id"], "authority", message.get("transcript", ""))
        elif msg_type == "response.output_audio_transcript.delta":
            self._append(message["item_id"], "assistant", message.get("delta", ""))
        elif msg_type == "response.output_audio_transcript.done":
            self._finish(message["item_id"], "assistant", message.get("transcript", ""))
        else:
            return False
        return True

    def flush(self) -> None:
        """The call is over: whatever is still mid-line is as final as it will get."""
        for item_id in self._order:
            line = self._lines[item_id]
            if not line["final"]:
                line["final"] = True
                self._publish(item_id)

    def heard_authority(self) -> bool:
        """Whether the other side has taken a turn yet. Their turn is counted when it is committed,
        before its transcription arrives, so a reply that is still being transcribed counts."""
        return any(line["role"] == "authority" for line in self._lines.values())

    def lines(self) -> list[dict[str, str]]:
        return [
            {"role": line["role"], "text": line["text"].strip()}
            for line in (self._lines[item_id] for item_id in self._order)
            if line["text"].strip()
        ]

    def _line(self, item_id: str, role: str) -> dict[str, Any]:
        line = self._lines.get(item_id)
        if line is None:
            line = {"role": role, "text": "", "final": False, "seq": len(self._order)}
            self._lines[item_id] = line
            self._order.append(item_id)
        return line

    def _append(self, item_id: str, role: str, delta: str) -> None:
        line = self._line(item_id, role)
        line["text"] += delta
        if self._clock() - self._last_sent.get(item_id, float("-inf")) >= self.THROTTLE_SECONDS:
            self._publish(item_id)

    def _finish(self, item_id: str, role: str, text: str) -> None:
        line = self._line(item_id, role)
        if text:
            line["text"] = text  # the completed transcript supersedes the accumulated deltas
        line["final"] = True
        print(f"[DEBUG sip {self.incident_id}] {role}: {line['text']!r}")
        self._publish(item_id)

    def _publish(self, item_id: str) -> None:
        line = self._lines[item_id]
        text = line["text"].strip()
        if not text:
            return
        self._last_sent[item_id] = self._clock()
        monitor.publish_transcript(
            self.incident_id, line["role"], text, item_id=item_id, seq=line["seq"], final=line["final"]
        )


async def accept_call(call_id: str, incident_id: str, report: dict[str, Any], authority: dict[str, Any]) -> None:
    instructions = build_dispatch_instructions(incident_id, report, authority)
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
    graph and stream the transcript. Runs until the call ends (either party hangs up) or
    the safety net fires."""
    import websockets

    result: dict[str, Any] = {
        "dispatch_confirmed": False,
        "outcome": "answered",
        "authority_statement": "",
        "raw_transcript": [],
    }
    live = LiveTranscript(incident_id)
    url = f"{_REALTIME_URL}?call_id={call_id}"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    safety_net_task: asyncio.Task | None = None

    async def _consume(ws) -> None:
        nonlocal safety_net_task
        async for raw in ws:
            message = json.loads(raw)
            if live.handle(message):
                continue
            msg_type = message.get("type")
            if msg_type == "response.function_call_arguments.done":
                if message.get("name") != RECORD_DISPATCH_CONFIRMATION_TOOL.name:
                    continue
                if not live.heard_authority():
                    # A decision nobody has spoken is not one. Seen on a call that reached voicemail:
                    # the model recorded a confirmation before any reply, and the incident closed as
                    # dispatched. Refuse it, and tell the model why, so the call carries on.
                    print(f"[DEBUG sip {incident_id}] refused a dispatch decision recorded before any reply")
                    await _send_tool_output(ws, message["call_id"], {"recorded": False, "reason": _NO_DECISION_HEARD})
                    continue
                args = json.loads(message["arguments"]) if message.get("arguments") else {}
                confirmed = bool(args.get("confirmed"))
                statement = str(args.get("statement", ""))
                result["dispatch_confirmed"] = confirmed
                result["authority_statement"] = statement
                monitor.publish(incident_id, {"type": "dispatch", "confirmed": confirmed, "statement": statement})
                await _send_tool_output(ws, message["call_id"], {"acknowledged": True})
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
        live.flush()

    result["raw_transcript"] = live.lines()
    await resume_incident(incident_id, result)


async def _send_tool_output(ws, call_id: str, output: dict[str, Any]) -> None:
    """Answers a tool call and lets the model speak again."""
    await ws.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": json.dumps(output, ensure_ascii=False)},
            }
        )
    )
    await ws.send(json.dumps({"type": "response.create"}))


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
