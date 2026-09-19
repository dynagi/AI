"""Configurable LLM provider (LLM_PROVIDER = gemini | openai | anthropic).

Only the provider you use needs its package/key. The agent and the categorizer depend on this factory,
never on a specific vendor.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.config import get_settings


class LLMUnavailable(RuntimeError):
    """No usable model is configured (missing key/package) or the provider is down."""


@lru_cache(maxsize=4)
def _build(provider: str, model: Optional[str], key: str):
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model or get_settings().gemini_model, google_api_key=key)
    if provider == "openai":
        from langchain_openai import ChatOpenAI  # pip install langchain-openai

        return ChatOpenAI(model=model or "gpt-4o-mini", api_key=key, temperature=0)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # pip install langchain-anthropic

        return ChatAnthropic(model=model or "claude-sonnet-4-5", api_key=key, temperature=0)
    raise LLMUnavailable(f"Unknown LLM_PROVIDER {provider!r}")


def get_llm():
    s = get_settings()
    provider = s.llm_provider.lower()
    key = {"gemini": s.gemini_api_key, "openai": s.openai_api_key, "anthropic": s.anthropic_api_key}.get(provider)
    if not key:
        raise LLMUnavailable(f"No API key configured for LLM_PROVIDER={provider!r}.")
    try:
        return _build(provider, s.llm_model, key)
    except ImportError as exc:
        raise LLMUnavailable(f"The package for LLM_PROVIDER={provider!r} is not installed: {exc}") from exc


def get_llm_or_none():
    try:
        return get_llm()
    except LLMUnavailable:
        return None
