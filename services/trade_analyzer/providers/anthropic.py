"""Anthropic LLM provider."""
from __future__ import annotations

import os

from .base import LLMProvider, ProviderError, ProviderTimeout, ProviderUnavailable


def _api_key() -> str:
    return (os.getenv("ANTHROPIC_API_KEY") or "").strip()


def _client():
    if not _api_key():
        raise ProviderUnavailable("ANTHROPIC_API_KEY not set")
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise ProviderUnavailable(f"anthropic package not installed: {exc}") from exc
    return anthropic.Anthropic(api_key=_api_key())


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-haiku-4-5-20251001"

    def generate(self, system_prompt, user_prompt, *, model, timeout_s, **opts):
        client = _client()
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=timeout_s,
            )
        except Exception as exc:
            name = type(exc).__name__
            if "Timeout" in name:
                raise ProviderTimeout(f"Anthropic timeout after {timeout_s}s: {exc}") from exc
            raise ProviderError(f"Anthropic call failed: {exc}") from exc

        try:
            return msg.content[0].text
        except (AttributeError, IndexError) as exc:
            raise ProviderError(f"Unexpected Anthropic response shape: {msg!r}") from exc

    def health_check(self):
        if not _api_key():
            return False, "ANTHROPIC_API_KEY not set"
        return True, "ANTHROPIC_API_KEY present"
