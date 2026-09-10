"""Single place that decides which concrete provider backs LLMProvider/TelephonyProvider.
Swapping providers (e.g. adding OpenAI later) means adding a branch here and setting
LLM_PROVIDER in the environment -- the graph and routes never import a concrete SDK."""

from __future__ import annotations

from functools import lru_cache

from agent.config import settings
from agent.providers.base import LLMProvider, TelephonyProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "mock":
        from agent.providers.mock_llm import MockLLMProvider

        return MockLLMProvider()
    if provider == "gemini":
        from agent.providers.gemini_llm import GeminiLLMProvider

        return GeminiLLMProvider()
    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Add a branch in agent/providers/factory.py "
        "to support a new provider (e.g. 'openai')."
    )


@lru_cache
def get_telephony_provider() -> TelephonyProvider:
    provider = settings.telephony_provider.lower()
    if provider == "mock":
        from agent.providers.mock_telephony import MockTelephonyProvider

        return MockTelephonyProvider()
    if provider == "twilio":
        from agent.providers.twilio_telephony import TwilioTelephonyProvider

        return TwilioTelephonyProvider()
    if provider == "signalwire":
        from agent.providers.signalwire_telephony import SignalWireTelephonyProvider

        return SignalWireTelephonyProvider()
    raise ValueError(f"Unknown TELEPHONY_PROVIDER={provider!r}.")
