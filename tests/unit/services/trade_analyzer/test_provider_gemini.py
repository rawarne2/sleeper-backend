"""GeminiProvider tests — google-genai SDK with thinking disabled."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.trade_analyzer.providers.base import (
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from services.trade_analyzer.providers.gemini import GeminiProvider


def _fake_response(text: str = '{"winner":"even","summary_bullets":[],"side_a":{},"side_b":{}}'):
    resp = MagicMock()
    resp.text = text
    return resp


def test_health_check_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    available, detail = GeminiProvider().health_check()
    assert available is False
    assert "GEMINI_API_KEY" in detail


def test_health_check_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")
    available, _ = GeminiProvider().health_check()
    assert available is True


def _build_fake_genai(capture: dict, response):
    class _FakeModels:
        def generate_content(self, **kw):
            capture.update(kw)
            if isinstance(response, Exception):
                raise response
            return response

    class _FakeClient:
        def __init__(self, *_, **__):
            self.models = _FakeModels()

    fake = MagicMock()
    fake.Client = _FakeClient
    return fake


def test_generate_sets_thinking_budget_zero(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")
    captured: dict = {}
    fake_genai = _build_fake_genai(captured, _fake_response())

    with patch.dict("sys.modules", {"google": MagicMock(genai=fake_genai)}):
        with patch("services.trade_analyzer.providers.gemini._import_genai",
                   return_value=(fake_genai, fake_genai.types)):
            out = GeminiProvider().generate(
                "sys", "user", model="gemini-2.5-flash", timeout_s=10
            )

    assert out.startswith("{")
    cfg = captured.get("config")
    assert cfg is not None
    # types.GenerateContentConfig is a MagicMock here, so attribute access works
    # for inspection; just check the kwargs the provider passed to it.
    # Inspect via _build_config call-args by checking the kwargs passed in.


def test_generate_calls_config_with_thinking_off_and_json(monkeypatch):
    """Inspect the kwargs handed to GenerateContentConfig: thinking off, JSON schema set."""
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")

    config_kwargs: dict = {}
    thinking_kwargs: dict = {}

    class _FakeThinkingConfig:
        def __init__(self, **kw):
            thinking_kwargs.update(kw)

    class _FakeHttpOptions:
        def __init__(self, **kw):
            pass

    class _FakeGenerateContentConfig:
        def __init__(self, **kw):
            config_kwargs.update(kw)

    class _FakeModels:
        def generate_content(self, **_kw):
            return _fake_response()

    class _FakeClient:
        def __init__(self, *_, **__):
            self.models = _FakeModels()

    fake_types = MagicMock()
    fake_types.ThinkingConfig = _FakeThinkingConfig
    fake_types.HttpOptions = _FakeHttpOptions
    fake_types.GenerateContentConfig = _FakeGenerateContentConfig

    fake_genai = MagicMock()
    fake_genai.Client = _FakeClient

    with patch("services.trade_analyzer.providers.gemini._import_genai",
               return_value=(fake_genai, fake_types)):
        GeminiProvider().generate(
            "sys", "user", model="gemini-2.5-flash", timeout_s=10
        )

    assert thinking_kwargs.get("thinking_budget") == 0, (
        f"thinking_budget should be 0, got {thinking_kwargs!r}"
    )
    assert config_kwargs.get("response_mime_type") == "application/json"
    assert config_kwargs.get("system_instruction") == "sys"
    assert config_kwargs.get("response_schema") is not None


def test_generate_propagates_timeout(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")

    class _Boom(Exception):
        pass
    _Boom.__name__ = "DeadlineExceeded"

    class _FakeModels:
        def generate_content(self, **_kw):
            raise _Boom("deadline exceeded")

    class _FakeClient:
        def __init__(self, *_, **__):
            self.models = _FakeModels()

    fake_genai = MagicMock()
    fake_genai.Client = _FakeClient
    fake_types = MagicMock()

    with patch("services.trade_analyzer.providers.gemini._import_genai",
               return_value=(fake_genai, fake_types)):
        with pytest.raises(ProviderTimeout):
            GeminiProvider().generate(
                "sys", "user", model="gemini-2.5-flash", timeout_s=1
            )


def test_generate_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable):
        GeminiProvider().generate("sys", "user", model="gemini-2.5-flash", timeout_s=1)


def test_generate_maps_429_to_rate_limited(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")

    class _TooManyRequests(Exception):
        pass

    class _FakeModels:
        def generate_content(self, **_kw):
            err = _TooManyRequests("429 Too Many Requests")
            err.code = 429  # type: ignore[attr-defined]
            raise err

    class _FakeClient:
        def __init__(self, *_, **__):
            self.models = _FakeModels()

    fake_genai = MagicMock()
    fake_genai.Client = _FakeClient
    fake_types = MagicMock()

    with patch("services.trade_analyzer.providers.gemini._import_genai",
               return_value=(fake_genai, fake_types)):
        with pytest.raises(ProviderRateLimited) as exc_info:
            GeminiProvider().generate(
                "sys", "user", model="gemini-2.0-flash", timeout_s=10
            )
    assert "429" in str(exc_info.value)
    assert exc_info.value.retry_after_seconds == 60


def test_generate_raises_on_empty_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")
    bad = MagicMock()
    bad.text = ""

    class _FakeModels:
        def generate_content(self, **_kw):
            return bad

    class _FakeClient:
        def __init__(self, *_, **__):
            self.models = _FakeModels()

    fake_genai = MagicMock()
    fake_genai.Client = _FakeClient
    fake_types = MagicMock()

    with patch("services.trade_analyzer.providers.gemini._import_genai",
               return_value=(fake_genai, fake_types)):
        with pytest.raises(ProviderError):
            GeminiProvider().generate(
                "sys", "user", model="gemini-2.5-flash", timeout_s=10
            )
