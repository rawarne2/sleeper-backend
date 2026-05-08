"""GeminiProvider tests."""
from unittest.mock import MagicMock, patch

import pytest

from services.trade_analyzer.providers.base import ProviderUnavailable
from services.trade_analyzer.providers.gemini import GeminiProvider


def test_health_check_unavailable_when_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    p = GeminiProvider()
    ok, detail = p.health_check()
    assert ok is False
    assert "GEMINI_API_KEY" in detail


def test_health_check_available_when_key_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    p = GeminiProvider()
    ok, _ = p.health_check()
    assert ok is True


def test_generate_returns_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    mock_model = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"fairness_score":50}'
    mock_model.generate_content.return_value = mock_resp
    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel",
        return_value=mock_model,
    ):
        p = GeminiProvider()
        out = p.generate("sys", "user", model="gemini-2.5-flash", timeout_s=10)
    assert out == '{"fairness_score":50}'
    mock_model.generate_content.assert_called_once()


def test_generate_raises_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    p = GeminiProvider()
    with pytest.raises(ProviderUnavailable):
        p.generate("sys", "user", model="gemini-2.5-flash", timeout_s=10)
