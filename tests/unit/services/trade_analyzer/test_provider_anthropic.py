"""AnthropicProvider tests."""
from unittest.mock import MagicMock, patch

import pytest

from services.trade_analyzer.providers.anthropic import AnthropicProvider
from services.trade_analyzer.providers.base import ProviderUnavailable


def test_health_check_unavailable_when_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()
    ok, detail = p.health_check()
    assert ok is False
    assert "ANTHROPIC_API_KEY" in detail


def test_health_check_available_when_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = AnthropicProvider()
    ok, _ = p.health_check()
    assert ok is True


def test_generate_returns_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    msg = MagicMock()
    block = MagicMock()
    block.text = '{"fairness_score":50}'
    msg.content = [block]
    fake_client.messages.create.return_value = msg
    with patch(
        "services.trade_analyzer.providers.anthropic._client",
        return_value=fake_client,
    ):
        p = AnthropicProvider()
        out = p.generate("sys", "user", model="claude-haiku-4-5-20251001", timeout_s=10)
    assert out == '{"fairness_score":50}'


def test_generate_raises_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()
    with pytest.raises(ProviderUnavailable):
        p.generate("sys", "user", model="claude-haiku-4-5-20251001", timeout_s=10)
