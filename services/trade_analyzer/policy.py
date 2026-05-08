"""Trade Analyzer routing: env-backed defaults and production Anthropic-only policy."""
from __future__ import annotations

import os

from services.trade_analyzer.providers.registry import known_providers


def anthropic_only_mode() -> bool:
    """Restrict to Anthropic when explicitly set or when running on Vercel production."""

    explicit = (os.getenv("TRADE_ANALYZER_ANTHROPIC_ONLY") or "").strip().lower()
    if explicit in ("1", "true", "yes"):
        return True
    if explicit in ("0", "false", "no"):
        return False
    return (os.getenv("VERCEL_ENV") or "").strip().lower() == "production"


def default_provider_raw() -> str:
    return (os.getenv("TRADE_ANALYZER_DEFAULT_PROVIDER") or "ollama").strip().lower()


def effective_default_provider() -> str:
    """Default provider surfaced to clients; production forces anthropic."""

    return "anthropic" if anthropic_only_mode() else default_provider_raw()


def default_model_for(provider: str) -> str:

    env_key = f"TRADE_ANALYZER_{provider.upper()}_MODEL"
    fallback = {
        "ollama": "qwen2.5:14b-instruct",
        "anthropic": "claude-sonnet-4-6",
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "echo": "echo",
    }.get(provider, "echo")
    raw = os.getenv(env_key)
    if raw is None or not str(raw).strip():
        raw = fallback
    return str(raw).strip()


def provider_names_for_listing() -> list[str]:
    """Providers returned by GET /providers (omit ollama/echo/etc. in prod)."""

    names = sorted(known_providers())
    if anthropic_only_mode():
        return [n for n in names if n == "anthropic"]
    return names


def environment_provider_error(body_provider: str | None) -> str | None:
    """Reject explicit non-Anthropic provider in production-capable deployments."""

    if not anthropic_only_mode():
        return None
    if body_provider is None:
        return None
    norm = body_provider.strip().lower()
    if norm != "anthropic":
        return (
            "Only the Anthropic provider is available in this environment. "
            "Omit the provider field from the request or send provider anthropic."
        )
    return None


def resolved_provider_and_model(
    *,
    body_provider: str | None,
    body_model: str | None,
) -> tuple[str, str]:
    """Apply production policy before calling the analyzer."""

    if anthropic_only_mode():
        return "anthropic", default_model_for("anthropic")
    prov = (body_provider or effective_default_provider()).strip().lower()
    mod = body_model.strip() if isinstance(body_model, str) else ""
    base = default_model_for(prov)
    return prov, mod if mod else base
