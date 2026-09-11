"""mu-law/PCM conversion for bridging Twilio's 8kHz mu-law Media Streams to Gemini
Live's 16kHz PCM16 input (and back for playback on the call)."""

from __future__ import annotations

try:
    import audioop  # stdlib, removed in Python 3.13+
except ModuleNotFoundError:  # pragma: no cover
    import audioop_lts as audioop  # drop-in backport, see requirements.txt


class TwilioAudioBridge:
    """Resamples one call's audio in both directions. audioop.ratecv must carry its
    filter state from one chunk to the next -- Twilio/Gemini both stream audio in small
    (~20ms) chunks, and reseeding the filter on every chunk (state=None) introduces an
    audible click/distortion at every chunk boundary, which degrades Gemini's ASR."""

    def __init__(self) -> None:
        self._to_gemini_state = None
        self._to_twilio_state = None

    def twilio_mulaw_to_pcm16(self, mulaw_bytes: bytes) -> bytes:
        """8kHz mu-law -> 16-bit PCM, then upsampled to 16kHz for Gemini Live input."""
        pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
        pcm_16k, self._to_gemini_state = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, self._to_gemini_state)
        return pcm_16k

    def pcm16_24k_to_twilio_mulaw(self, pcm_bytes: bytes) -> bytes:
        """Gemini Live outputs 24kHz PCM16; downsample to 8kHz mu-law for the phone call."""
        pcm_8k, self._to_twilio_state = audioop.ratecv(pcm_bytes, 2, 1, 24000, 8000, self._to_twilio_state)
        return audioop.lin2ulaw(pcm_8k, 2)
