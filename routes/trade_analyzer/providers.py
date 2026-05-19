"""GET /api/trade-analyzer/providers."""
from __future__ import annotations

import os

from flask import jsonify

from routes.helpers import with_error_handling
from services.trade_analyzer import policy as ta_policy
from services.trade_analyzer.providers.registry import get_provider

from . import trade_analyzer_bp


def _enabled() -> bool:
    return (os.getenv("TRADE_ANALYZER_ENABLED", "true").strip().lower()
            not in ("0", "false", "no"))


@trade_analyzer_bp.route("/providers", methods=["GET"])
@with_error_handling
def list_providers():
    entries = []
    for name in ta_policy.provider_names_for_listing():
        try:
            instance = get_provider(name)
            available, detail = instance.health_check()
            entries.append({
                "name": name,
                "default_model": ta_policy.default_model_for(name),
                "models": ta_policy.models_for_provider_listing(
                    name, available=bool(available), instance=instance
                ),
                "available": bool(available),
                "detail": detail,
            })
        except Exception as exc:
            entries.append({
                "name": name,
                "default_model": "",
                "models": [],
                "available": False,
                "detail": f"factory error: {exc}",
            })
    return jsonify({
        "default_provider": ta_policy.effective_default_provider(),
        "allows_client_provider_model_choice": not ta_policy.production_routing_locked(),
        "providers": entries,
        "rate_limit": {
            "per_hour": int(os.getenv("TRADE_ANALYZER_RATE_LIMIT_PER_HOUR", "20")),
            "key": os.getenv("TRADE_ANALYZER_RATE_LIMIT_KEY", "ip"),
        },
        "enabled": _enabled(),
    })
