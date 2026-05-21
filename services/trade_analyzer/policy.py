"""Trade Analyzer routing: env-backed defaults and production Gemini routing."""
from __future__ import annotations

import os

from services.trade_analyzer.providers.base import LLMProvider
from services.trade_analyzer.providers.registry import get_provider, known_providers

PRODUCTION_DEFAULT_PROVIDER = "gemini"
# Shown in production GET /providers; only Gemini is routable.
PRODUCTION_PROVIDER_DISPLAY_ORDER = ("gemini", "anthropic", "echo", "ollama")


def _production_lock_from_env() -> bool | None:
    """Explicit override via TRADE_ANALYZER_PRODUCTION_LOCK."""

    raw = (os.getenv("TRADE_ANALYZER_PRODUCTION_LOCK") or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return None


def production_routing_locked() -> bool:
    """Lock routing to Gemini and hide client provider/model choice in production."""

    explicit = _production_lock_from_env()
    if explicit is not None:
        return explicit
    return (os.getenv("VERCEL_ENV") or "").strip().lower() == "production"


def default_provider_raw() -> str:
    return (os.getenv("TRADE_ANALYZER_DEFAULT_PROVIDER") or "ollama").strip().lower()


def effective_default_provider() -> str:
    """Default provider surfaced to clients; production forces Gemini."""

    return PRODUCTION_DEFAULT_PROVIDER if production_routing_locked() else default_provider_raw()


# Dev UI selectable models when TRADE_ANALYZER_{PROVIDER}_MODELS is unset.
_STATIC_SELECTABLE_MODELS: dict[str, tuple[str, ...]] = {
    "anthropic": ("claude-sonnet-4-6", "claude-haiku-4-5"),
    "gemini": ("gemini-2.5-flash", "gemini-2.0-flash"),
    "echo": ("echo",),
    "ollama": ("qwen2.5:14b-instruct", "llama3.1:8b"),
}


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


def models_for_provider_listing(
    provider: str,
    *,
    available: bool,
    instance: LLMProvider | None = None,
) -> list[str]:
    """Models the dashboard may offer for this provider (empty when unavailable)."""

    if not available:
        return []

    default = default_model_for(provider)
    env_key = f"TRADE_ANALYZER_{provider.upper()}_MODELS"
    env_raw = (os.getenv(env_key) or "").strip()

    if env_raw:
        raw_models = [m.strip() for m in env_raw.split(",") if m.strip()]
    elif provider == "ollama":
        if instance is None:
            try:
                instance = get_provider("ollama")
            except Exception:
                instance = None
        list_fn = getattr(instance, "list_models",
                          None) if instance is not None else None
        discovered = list(list_fn()) if callable(list_fn) else []
        raw_models = list(_STATIC_SELECTABLE_MODELS.get("ollama", ()))
        for name in discovered:
            if name not in raw_models:
                raw_models.append(name)
    else:
        raw_models = list(_STATIC_SELECTABLE_MODELS.get(provider, ()))

    if default and default not in raw_models:
        raw_models.insert(0, default)
    elif not raw_models and default:
        raw_models = [default]

    seen: set[str] = set()
    out: list[str] = []
    for name in raw_models:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def client_model_selection_error(provider: str, model: str | None) -> str | None:
    """Reject unknown client model strings in dev (production ignores client choice)."""

    if production_routing_locked():
        return None
    if model is None or not str(model).strip():
        return None
    chosen = str(model).strip()
    prov = provider.strip().lower()
    try:
        instance = get_provider(prov)
        available, _ = instance.health_check()
    except Exception:
        available = False
        instance = None
    allowed = models_for_provider_listing(
        prov, available=available, instance=instance)
    if not allowed:
        return f"Provider {prov!r} has no selectable models right now."
    if chosen not in allowed:
        return f"Model {chosen!r} is not available for provider {prov!r}."
    return None


def provider_names_for_listing() -> list[str]:
    """Providers returned by GET /providers (curated list in prod for UI)."""

    names = set(known_providers())
    if production_routing_locked():
        return [n for n in PRODUCTION_PROVIDER_DISPLAY_ORDER if n in names]
    return sorted(names)


def environment_provider_error(body_provider: str | None) -> str | None:
    """Reject explicit non-Gemini provider in production-capable deployments."""

    if not production_routing_locked():
        return None
    if body_provider is None:
        return None
    norm = body_provider.strip().lower()
    if norm != PRODUCTION_DEFAULT_PROVIDER:
        return (
            "Only the Gemini provider is available in this environment. "
            "Omit the provider field from the request or send provider gemini."
        )
    return None


def resolved_provider_and_model(
    *,
    body_provider: str | None,
    body_model: str | None,
) -> tuple[str, str]:
    """Apply production policy before calling the analyzer."""

    if production_routing_locked():
        return PRODUCTION_DEFAULT_PROVIDER, default_model_for(PRODUCTION_DEFAULT_PROVIDER)
    prov = (body_provider or effective_default_provider()).strip().lower()
    mod = body_model.strip() if isinstance(body_model, str) else ""
    if mod:
        err = client_model_selection_error(prov, mod)
        if err:
            mod = ""
    base = default_model_for(prov)
    return prov, mod if mod else base


def trade_analyzer_debug_log_enabled() -> bool:
    """When true, log parsed request and full LLM prompts (local dev only)."""

    return (os.getenv("TRADE_ANALYZER_DEBUG_LOG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
