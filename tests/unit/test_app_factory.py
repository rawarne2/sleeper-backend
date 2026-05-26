"""Tests for the shared app factory."""
import pytest


def test_create_app_returns_configured_flask_app():
    """Factory creates a Flask app with the given DB URL."""
    from app_factory import create_app
    app = create_app(db_url="sqlite:///:memory:")
    assert app is not None
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"
    assert app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] is False


def test_factory_registers_all_blueprints():
    """All 10 route blueprints are registered."""
    from app_factory import create_app
    app = create_app(db_url="sqlite:///:memory:")
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    expected_prefixes = [
        "health", "ktc_rankings", "ktc_bulk", "sleeper_players",
        "sleeper_leagues", "sleeper_research", "sleeper_stats",
        "maintenance", "dashboard", "trade_analyzer",
    ]
    for prefix in expected_prefixes:
        assert any(prefix in ep for ep in endpoints), f"Blueprint '{prefix}' not registered"


def test_factory_accepts_engine_options():
    """Engine options are forwarded to SQLAlchemy config."""
    from app_factory import create_app
    opts = {"pool_pre_ping": True}
    app = create_app(db_url="sqlite:///:memory:", engine_options=opts)
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_pre_ping"] is True


def test_factory_accepts_swagger_config():
    """Swagger host and schemes are wired up (the /docs/ route is registered)."""
    from app_factory import create_app
    app = create_app(
        db_url="sqlite:///:memory:",
        swagger_host="example.com",
        swagger_schemes=["https"],
    )
    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert any("/docs" in rule for rule in rules), "/docs/ route missing — setup_swagger not called"


def test_factory_omits_engine_options_when_none():
    """No caller-supplied engine options are set when engine_options is None."""
    from app_factory import create_app
    app = create_app(db_url="sqlite:///:memory:", engine_options=None)
    # Flask-SQLAlchemy may set the key to {} itself; what matters is that the
    # factory did not inject any caller-supplied options.
    assert not app.config.get("SQLALCHEMY_ENGINE_OPTIONS")


def test_factory_omits_engine_options_when_empty_dict():
    """No caller-supplied engine options are set when engine_options is an empty dict."""
    from app_factory import create_app
    app = create_app(db_url="sqlite:///:memory:", engine_options={})
    # Flask-SQLAlchemy may set the key to {} itself; what matters is that the
    # factory did not inject any caller-supplied options.
    assert not app.config.get("SQLALCHEMY_ENGINE_OPTIONS")
