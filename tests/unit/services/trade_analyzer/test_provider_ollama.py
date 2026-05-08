"""OllamaProvider tests."""
from unittest.mock import MagicMock, patch

import pytest

from services.trade_analyzer.providers.base import ProviderTimeout
from services.trade_analyzer.providers.ollama import OllamaProvider, _host


def test_host_rewrite_localhost_inside_container(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("OLLAMA_USE_LOCALHOST_IN_CONTAINER", raising=False)
    with patch("services.trade_analyzer.providers.ollama._is_container_environment", return_value=True):
        assert _host() == "http://host.docker.internal:11434"


def test_host_no_rewrite_when_escaping_rewrite(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_USE_LOCALHOST_IN_CONTAINER", "1")
    with patch("services.trade_analyzer.providers.ollama._is_container_environment", return_value=True):
        assert _host() == "http://localhost:11434"


def test_host_no_rewrite_when_not_container(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("OLLAMA_USE_LOCALHOST_IN_CONTAINER", raising=False)
    with patch("services.trade_analyzer.providers.ollama._is_container_environment", return_value=False):
        assert _host() == "http://localhost:11434"


def test_generate_returns_message_content():
    fake_client = MagicMock()
    fake_client.chat.return_value = {"message": {"content": '{"fairness_score":50}'}}
    with patch("services.trade_analyzer.providers.ollama._client", return_value=fake_client):
        p = OllamaProvider()
        out = p.generate("sys", "user", model="qwen2.5:14b-instruct", timeout_s=10)
    assert out == '{"fairness_score":50}'
    fake_client.chat.assert_called_once()
    _kwargs = fake_client.chat.call_args.kwargs
    assert "format" in _kwargs


def test_generate_falls_back_when_schema_unsupported():
    fake_client = MagicMock()
    fake_client.chat.side_effect = [
        ValueError("schema not supported"),
        {"message": {"content": '{"fairness_score":50}'}},
    ]
    with patch("services.trade_analyzer.providers.ollama._client", return_value=fake_client):
        p = OllamaProvider()
        out = p.generate("sys", "user", model="qwen2.5:14b-instruct", timeout_s=10)
    assert out == '{"fairness_score":50}'
    assert fake_client.chat.call_count == 2


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
