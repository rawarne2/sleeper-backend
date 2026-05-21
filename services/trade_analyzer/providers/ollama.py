"""Ollama LLM provider — local-only."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from services.trade_analyzer.output_schema import TRADE_ANALYZER_JSON_SCHEMA

from .base import LLMProvider, ProviderError, ProviderTimeout, ProviderUnavailable

_LOOPBACK_MARKERS = frozenset(("localhost", "127.0.0.1", "::1"))

_DEFAULT_URL = "http://localhost:11434"


def _is_container_environment() -> bool:
    """True inside Linux containers (.dockerenv is present when not using rootless quirks)."""
    try:
        return Path("/.dockerenv").exists()
    except OSError:
        return False


def _host() -> str:
    raw = (os.getenv("OLLAMA_HOST") or _DEFAULT_URL).strip()

    escape = (os.getenv("OLLAMA_USE_LOCALHOST_IN_CONTAINER") or "").strip().lower()
    if escape in ("1", "true", "yes"):
        return raw

    if not _is_container_environment():
        return raw

    try:
        parsed = urlparse(raw)
    except Exception:
        return raw

    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_MARKERS:
        return raw

    port = parsed.port
    netloc = "host.docker.internal" if port is None else f"host.docker.internal:{port}"
    return urlunparse(
        (
            parsed.scheme or "http",
            netloc,
            parsed.path or "",
            parsed.params,
            parsed.query,
            parsed.fragment,
        ),
    )


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
            # Structured outputs (JSON Schema) prevent shape drift vs plain format="json".
            resp = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={"temperature": 0.2},
                format=TRADE_ANALYZER_JSON_SCHEMA,
            )
        except TimeoutError as exc:
            raise ProviderTimeout(f"Ollama timeout after {timeout_s}s: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Ollama call failed: {exc}") from exc

        try:
            return resp["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Unexpected Ollama response shape: {resp!r}") from exc

    def list_models(self) -> list[str]:
        """Installed Ollama model names from ``Client.list()``."""
        try:
            resp = _client().list()
        except Exception:
            return []
        raw = resp.get("models") if isinstance(resp, dict) else getattr(resp, "models", None)
        if not isinstance(raw, list):
            return []
        names: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name")
            else:
                name = getattr(item, "name", None)
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        return sorted(set(names))

    def health_check(self):
        try:
            _client().list()
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"host={_host()}"
