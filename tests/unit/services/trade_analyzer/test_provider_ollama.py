"""OllamaProvider tests."""
from unittest.mock import MagicMock, patch

import pytest

from services.trade_analyzer.providers.base import ProviderTimeout
from services.trade_analyzer.providers.ollama import OllamaProvider


def test_generate_returns_message_content():
    fake_client = MagicMock()
    fake_client.chat.return_value = {"message": {"content": '{"fairness_score":50}'}}
    with patch("services.trade_analyzer.providers.ollama._client", return_value=fake_client):
        p = OllamaProvider()
        out = p.generate("sys", "user", model="qwen2.5:14b-instruct", timeout_s=10)
    assert out == '{"fairness_score":50}'
    fake_client.chat.assert_called_once()


def test_generate_translates_timeout():
    fake_client = MagicMock()
    fake_client.chat.side_effect = TimeoutError("slow")
    with patch("services.trade_analyzer.providers.ollama._client", return_value=fake_client):
        p = OllamaProvider()
        with pytest.raises(ProviderTimeout):
            p.generate("sys", "user", model="m", timeout_s=1)


def test_health_check_pings_tags():
    fake_client = MagicMock()
    fake_client.list.return_value = {"models": [{"name": "qwen2.5:14b-instruct"}]}
    with patch("services.trade_analyzer.providers.ollama._client", return_value=fake_client):
        p = OllamaProvider()
        ok, detail = p.health_check()
    assert ok is True
    assert "host=" in detail


def test_health_check_marks_unavailable_when_client_raises():
    with patch("services.trade_analyzer.providers.ollama._client", side_effect=ConnectionError("nope")):
        p = OllamaProvider()
        ok, detail = p.health_check()
    assert ok is False
    assert "nope" in detail or "ConnectionError" in detail
