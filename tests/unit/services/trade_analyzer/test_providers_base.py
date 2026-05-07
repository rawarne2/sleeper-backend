"""Provider base + registry + EchoProvider."""
import json

import pytest

from services.trade_analyzer.providers.base import (
    LLMProvider,
    ProviderUnavailable,
)
from services.trade_analyzer.providers.echo import EchoProvider
from services.trade_analyzer.providers.registry import get_provider


def test_echo_provider_returns_fixture_json(echo_fixture):
    p = EchoProvider()
    raw = p.generate("sys", "user", model="echo", timeout_s=1)
    parsed = json.loads(raw)
    assert parsed == echo_fixture


def test_echo_provider_health_check_available():
    p = EchoProvider()
    available, detail = p.health_check()
    assert available is True
    assert "echo" in detail.lower()


def test_registry_returns_known_provider_instance():
    instance = get_provider("echo")
    assert isinstance(instance, EchoProvider)


def test_registry_unknown_provider_raises():
    with pytest.raises(ProviderUnavailable):
        get_provider("does-not-exist")


def test_llm_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()
