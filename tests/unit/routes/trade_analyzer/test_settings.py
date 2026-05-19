"""Unit tests for `services.trade_analyzer.policy`."""
import pytest


@pytest.fixture
def prod_env(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_PRODUCTION_LOCK", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "production")


@pytest.fixture
def dev_env(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_PRODUCTION_LOCK", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)


def test_production_lock_follows_vercel_prod(prod_env):
    from services.trade_analyzer.policy import production_routing_locked

    assert production_routing_locked() is True


def test_production_lock_off_when_not_vercel_prod(dev_env):
    from services.trade_analyzer.policy import production_routing_locked

    assert production_routing_locked() is False


def test_production_lock_explicit_override_yes(monkeypatch, dev_env):
    monkeypatch.setenv("TRADE_ANALYZER_PRODUCTION_LOCK", "true")

    from services.trade_analyzer.policy import production_routing_locked

    assert production_routing_locked() is True


def test_production_lock_explicit_override_no(monkeypatch, prod_env):
    monkeypatch.setenv("TRADE_ANALYZER_PRODUCTION_LOCK", "false")

    from services.trade_analyzer.policy import production_routing_locked

    assert production_routing_locked() is False


def test_provider_names_filtered_in_prod(monkeypatch, prod_env):
    from services.trade_analyzer.policy import provider_names_for_listing

    assert provider_names_for_listing() == ["gemini", "anthropic", "echo", "ollama"]


def test_resolved_provider_ignores_client_in_prod(monkeypatch, prod_env):
    from services.trade_analyzer.policy import resolved_provider_and_model

    prov, model = resolved_provider_and_model(body_provider="ollama", body_model="custom-model")
    assert prov == "gemini"
    assert isinstance(model, str)
    assert model


def test_environment_provider_error_explicit_non_gemini(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    err = environment_provider_error("echo")
    assert err is not None
    assert "Gemini" in err


def test_environment_provider_error_omit_ok(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    assert environment_provider_error(None) is None


def test_environment_provider_error_explicit_gemini_ok(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    assert environment_provider_error("gemini") is None


def test_environment_provider_error_explicit_anthropic_rejected(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    assert environment_provider_error("anthropic") is not None
