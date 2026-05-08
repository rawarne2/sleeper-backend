"""Unit tests for `services.trade_analyzer.policy`."""
import pytest


@pytest.fixture
def prod_env(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_ANTHROPIC_ONLY", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "production")


@pytest.fixture
def dev_env(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_ANTHROPIC_ONLY", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)


def test_anthropic_only_follows_vercel_prod(prod_env):
    from services.trade_analyzer.policy import anthropic_only_mode

    assert anthropic_only_mode() is True


def test_anthropic_only_off_when_not_vercel_prod(dev_env):
    from services.trade_analyzer.policy import anthropic_only_mode

    assert anthropic_only_mode() is False


def test_anthropic_only_explicit_override_yes(monkeypatch, dev_env):
    monkeypatch.setenv("TRADE_ANALYZER_ANTHROPIC_ONLY", "true")

    from services.trade_analyzer.policy import anthropic_only_mode

    assert anthropic_only_mode() is True


def test_anthropic_only_explicit_override_no(monkeypatch, prod_env):
    monkeypatch.setenv("TRADE_ANALYZER_ANTHROPIC_ONLY", "false")

    from services.trade_analyzer.policy import anthropic_only_mode

    assert anthropic_only_mode() is False


def test_provider_names_filtered_in_prod(monkeypatch, prod_env):
    from services.trade_analyzer.policy import provider_names_for_listing

    assert provider_names_for_listing() == ["anthropic"]


def test_resolved_provider_ignores_client_in_prod(monkeypatch, prod_env):
    from services.trade_analyzer.policy import resolved_provider_and_model

    prov, model = resolved_provider_and_model(body_provider="ollama", body_model="custom-model")
    assert prov == "anthropic"
    assert isinstance(model, str)
    assert model


def test_environment_provider_error_explicit_non_anthropic(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    err = environment_provider_error("echo")
    assert err is not None
    assert "Anthropic" in err


def test_environment_provider_error_omit_ok(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    assert environment_provider_error(None) is None


def test_environment_provider_error_explicit_anthropic_ok(prod_env):
    from services.trade_analyzer.policy import environment_provider_error

    assert environment_provider_error("anthropic") is None
