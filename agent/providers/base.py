"""Provider-agnostic interfaces. LangGraph nodes only ever talk to these abstractions,
never to a concrete Gemini/Twilio SDK directly -- swapping LLM_PROVIDER or
TELEPHONY_PROVIDER in config is enough to change backend without touching graph code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class VoiceEvent:
    type: Literal["audio", "transcript", "tool_call", "turn_complete", "closed"]
    audio: bytes | None = None
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_call_id: str | None = None
    """Echoed back verbatim in send_tool_response -- required by the Live API to match
    a response to its call when several tool calls arrive in the same turn."""


class VoiceSession(ABC):
    """One realtime, duplex conversation (employee collection call or authority call)."""

    @abstractmethod
    async def start(self, system_instruction: str, tools: list[ToolSpec]) -> None: ...

    @abstractmethod
    async def send_audio_chunk(self, pcm16_bytes: bytes) -> None: ...

    @abstractmethod
    async def send_text(self, text: str) -> None:
        """Text-mode input, used by the mock provider and for testing without audio."""

    @abstractmethod
    def receive_events(self) -> AsyncIterator[VoiceEvent]: ...

    @abstractmethod
    async def send_tool_response(self, tool_name: str, response: dict[str, Any], tool_call_id: str | None = None) -> None:
        """Acknowledges a tool_call event so the model's turn can continue, optionally
        carrying state back (e.g. which fields are still missing). Pass the event's
        tool_call_id through unchanged -- required by real Live API providers."""

    @abstractmethod
    async def close(self) -> None: ...


class LLMProvider(ABC):
    @abstractmethod
    async def generate_report_narrative(self, report_data: dict[str, Any]) -> str:
        """Human-readable incident summary. Must not touch detected_class/confidence."""

    @abstractmethod
    async def suggest_severity_and_action(self, report_data: dict[str, Any]) -> tuple[str, str]:
        """Returns (severity, recommended_action). Advisory only -- never overrides
        the employee's verification_status."""

    @abstractmethod
    def create_voice_session(self) -> VoiceSession: ...


class TelephonyProvider(ABC):
    @abstractmethod
    async def place_call(self, to_number: str, incident_id: str) -> str:
        """Initiates an outbound call, returns a call_sid/identifier."""

    @abstractmethod
    def build_stream_twiml(self, incident_id: str) -> str:
        """TwiML returned to Twilio's voice webhook, connecting the call audio to our
        media-stream websocket for the given incident."""
