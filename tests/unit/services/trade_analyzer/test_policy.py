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


def test_models_for_provider_listing_ollama_env_only(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_OLLAMA_MODELS", raising=False)
    monkeypatch.setenv("TRADE_ANALYZER_OLLAMA_MODEL", "qwen2.5:14b-instruct")

    models = policy.models_for_provider_listing("ollama", available=True)
    assert models == ["qwen2.5:14b-instruct"]


def test_models_for_provider_listing_ollama_respects_models_env(monkeypatch):
    monkeypatch.setenv(
        "TRADE_ANALYZER_OLLAMA_MODELS",
        "qwen2.5:14b-instruct,gemma3:27b",
    )
    monkeypatch.setenv("TRADE_ANALYZER_OLLAMA_MODEL", "qwen2.5:14b-instruct")

    models = policy.models_for_provider_listing("ollama", available=True)
    assert models == ["qwen2.5:14b-instruct", "gemma3:27b"]
