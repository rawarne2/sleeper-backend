"""Google Gemini LLM provider."""
from __future__ import annotations

import os

from .base import LLMProvider, ProviderError, ProviderTimeout, ProviderUnavailable


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.5-flash"

    def generate(self, system_prompt, user_prompt, *, model, timeout_s, **opts):
        if not _api_key():
            raise ProviderUnavailable("GEMINI_API_KEY not set")
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise ProviderUnavailable(f"google-generativeai package not installed: {exc}") from exc

        genai.configure(api_key=_api_key())
        gm = genai.GenerativeModel(model_name=model, system_instruction=system_prompt)

        try:
            resp = gm.generate_content(
                user_prompt,
                request_options={"timeout": timeout_s},
                generation_config={"temperature": 0.2},
            )
        except Exception as exc:
            name = type(exc).__name__
            msg = str(exc).lower()
            if (
                "Timeout" in name
                or "DeadlineExceeded" in name
                or "deadline exceeded" in msg
            ):
                raise ProviderTimeout(f"Gemini timeout after {timeout_s}s: {exc}") from exc
            raise ProviderError(f"Gemini call failed: {exc}") from exc

        text = getattr(resp, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"Unexpected Gemini response shape: {resp!r}")

        return text

    def health_check(self):
        if not _api_key():
            return False, "GEMINI_API_KEY not set"
        return True, "GEMINI_API_KEY present"
