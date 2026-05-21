"""Google Gemini LLM provider (google-genai SDK)."""
from __future__ import annotations

import os

from services.trade_analyzer.output_schema import TRADE_ANALYZER_JSON_SCHEMA

from .base import (
    LLMProvider,
    ProviderError,
    ProviderUnavailable,
    map_provider_call_error,
)


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def _thinking_budget() -> int:
    """0 disables thinking on gemini-2.5-flash; raise to allow capped reasoning."""
    try:
        return int(os.getenv("TRADE_ANALYZER_GEMINI_THINKING_BUDGET", "0"))
    except (TypeError, ValueError):
        return 0


def _max_output_tokens() -> int:
    try:
        return int(os.getenv("TRADE_ANALYZER_GEMINI_MAX_OUTPUT_TOKENS", "2048"))
    except (TypeError, ValueError):
        return 2048


def _import_genai():
    """Indirection to make patching easier in tests."""
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError as exc:
        raise ProviderUnavailable(
            f"google-genai package not installed: {exc}"
        ) from exc
    return genai, types


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.5-flash"

    def generate(self, system_prompt, user_prompt, *, model, timeout_s, **opts):
        if not _api_key():
            raise ProviderUnavailable("GEMINI_API_KEY not set")
        genai, types = _import_genai()

        client = genai.Client(api_key=_api_key())

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=TRADE_ANALYZER_JSON_SCHEMA,
            max_output_tokens=_max_output_tokens(),
            thinking_config=types.ThinkingConfig(thinking_budget=_thinking_budget()),
            http_options=types.HttpOptions(timeout=timeout_s * 1000),
        )

        try:
            resp = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            map_provider_call_error(exc, provider="Gemini", timeout_s=timeout_s)

        text = getattr(resp, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"Unexpected Gemini response shape: {resp!r}")

        return text

    def health_check(self):
        if not _api_key():
            return False, "GEMINI_API_KEY not set"
        return True, "GEMINI_API_KEY present"
