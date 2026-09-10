"""mu-law/PCM conversion for bridging Twilio's 8kHz mu-law Media Streams to Gemini
Live's 16kHz PCM16 input (and back for playback on the call)."""

from __future__ import annotations

try:
    import audioop  # stdlib, removed in Python 3.13+
except ModuleNotFoundError:  # pragma: no cover
    import audioop_lts as audioop  # drop-in backport, see requirements.txt


def twilio_mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """8kHz mu-law -> 16-bit PCM, then upsampled to 16kHz for Gemini Live input."""
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
    return pcm_16k


def pcm16_24k_to_twilio_mulaw(pcm_bytes: bytes) -> bytes:
    """Gemini Live outputs 24kHz PCM16; downsample to 8kHz mu-law for the phone call."""
    pcm_8k, _ = audioop.ratecv(pcm_bytes, 2, 1, 24000, 8000, None)
    return audioop.lin2ulaw(pcm_8k, 2)
