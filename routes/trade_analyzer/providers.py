"""GET /api/trade-analyzer/providers."""
from __future__ import annotations

import os

from flask import jsonify

from routes.helpers import with_error_handling
from services.trade_analyzer.providers.registry import get_provider, known_providers

from . import trade_analyzer_bp


def _enabled() -> bool:
    return (os.getenv("TRADE_ANALYZER_ENABLED", "true").strip().lower()
            not in ("0", "false", "no"))


def _default_provider() -> str:
    return os.getenv("TRADE_ANALYZER_DEFAULT_PROVIDER", "ollama").strip().lower()


@trade_analyzer_bp.route("/providers", methods=["GET"])
@with_error_handling
def list_providers():
    entries = []
    for name in known_providers():
        try:
            instance = get_provider(name)
            available, detail = instance.health_check()
            entries.append({
                "name": name,
                "default_model": instance.default_model,
                "available": bool(available),
                "detail": detail,
            })
        except Exception as exc:
            entries.append({
                "name": name, "default_model": "",
                "available": False, "detail": f"factory error: {exc}",
            })
    return jsonify({
        "default_provider": _default_provider(),
        "providers": entries,
        "rate_limit": {
            "per_hour": int(os.getenv("TRADE_ANALYZER_RATE_LIMIT_PER_HOUR", "20")),
            "key": os.getenv("TRADE_ANALYZER_RATE_LIMIT_KEY", "ip"),
        },
        "enabled": _enabled(),
    })
