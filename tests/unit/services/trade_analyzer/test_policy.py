"""Policy: selectable models and provider defaults."""
from __future__ import annotations

from services.trade_analyzer import policy


def test_gemini_static_models_excludes_25_pro():
    models = policy._STATIC_SELECTABLE_MODELS["gemini"]
    assert "gemini-2.5-pro" not in models
    assert "gemini-2.5-flash" in models
    assert "gemini-2.0-flash" in models


def test_default_model_for_gemini(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_GEMINI_MODEL", raising=False)
    assert policy.default_model_for("gemini") == "gemini-2.5-flash"
