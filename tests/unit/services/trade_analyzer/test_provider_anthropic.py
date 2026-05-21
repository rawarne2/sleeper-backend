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
    block.text = '{"winner":"even","summary_bullets":[],"side_a":{},"side_b":{}}'
    msg.content = [block]
    fake_client.messages.create.return_value = msg
    with patch(
        "services.trade_analyzer.providers.anthropic._client",
        return_value=fake_client,
    ):
        p = AnthropicProvider()
        out = p.generate("sys", "user", model="claude-sonnet-4-6", timeout_s=10)
    assert "winner" in out


def test_generate_raises_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()
    with pytest.raises(ProviderUnavailable):
        p.generate("sys", "user", model="claude-sonnet-4-6", timeout_s=10)


def test_generate_marks_system_prompt_for_caching(monkeypatch):
    """System prompt must be sent as a cache-eligible block."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    msg = MagicMock()
    block = MagicMock()
    block.text = '{"winner":"even","summary_bullets":[],"side_a":{},"side_b":{}}'
    msg.content = [block]
    fake_client.messages.create.return_value = msg
    with patch(
        "services.trade_analyzer.providers.anthropic._client",
        return_value=fake_client,
    ):
        p = AnthropicProvider()
        p.generate("SYSTEM TEXT", "USER TEXT", model="claude-sonnet-4-6", timeout_s=15)

    kwargs = fake_client.messages.create.call_args.kwargs
    system = kwargs.get("system")
    assert isinstance(system, list), "system must be a list of blocks for caching"
    assert system[0]["type"] == "text"
    assert system[0]["text"] == "SYSTEM TEXT"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # Tighter cap on output tokens — schema bounds the response in practice.
    assert kwargs.get("max_tokens") == 2048
