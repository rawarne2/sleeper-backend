"""Ollama LLM provider — local-only."""
from __future__ import annotations

import os

from .base import LLMProvider, ProviderError, ProviderTimeout, ProviderUnavailable


def _host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()


def _client():
    try:
        from ollama import Client  # type: ignore
    except ImportError as exc:
        raise ProviderUnavailable(f"ollama package not installed: {exc}") from exc
    return Client(host=_host())


class OllamaProvider(LLMProvider):
    name = "ollama"
    default_model = "qwen2.5:14b-instruct"

    def generate(self, system_prompt, user_prompt, *, model, timeout_s, **opts):
        client = _client()
        try:
            resp = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={"temperature": 0.2},
            )
        except TimeoutError as exc:
            raise ProviderTimeout(f"Ollama timeout after {timeout_s}s: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Ollama call failed: {exc}") from exc

        try:
            return resp["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Unexpected Ollama response shape: {resp!r}") from exc

    def health_check(self):
        try:
            _client().list()
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"host={_host()}"
