"""Parse and validate /api/trade-analyzer request bodies."""
from __future__ import annotations

from typing import Any, Dict

from data_types.trade_analyzer_types import KTCConfig, TradeRequest, TradeSide
from services.trade_analyzer.picks import PickIdError, parse_pick_id
from services.trade_analyzer.providers.registry import known_providers

_VALID_FORMATS = {"1qb", "superflex"}
_KNOWN_PROVIDERS = frozenset(known_providers())
_VALID_TEP = {"", "tep", "tepp", "teppp", None}

_DEFAULT_KTC: KTCConfig = {
    "league_format": "superflex",
    "is_redraft": False,
    "tep_level": "tep",
}


class RequestValidationError(ValueError):
    """Raised when the request body fails validation. Maps to HTTP 400."""


def _require(body: Dict[str, Any], key: str) -> Any:
    if key not in body or body[key] in (None, ""):
        raise RequestValidationError(f"Missing required field: {key}")
    return body[key]


def _parse_side(name: str, raw: Any) -> TradeSide:
    if not isinstance(raw, dict):
        raise RequestValidationError(f"{name} must be an object")
    if "roster_id" not in raw:
        raise RequestValidationError(f"{name}.roster_id is required")
    rid = raw["roster_id"]
    if not isinstance(rid, int):
        raise RequestValidationError(f"{name}.roster_id must be an integer")
    player_ids = raw.get("player_ids") or []
    pick_ids = raw.get("pick_ids") or []
    if not isinstance(player_ids, list) or not all(isinstance(x, str) for x in player_ids):
        raise RequestValidationError(
            f"{name}.player_ids must be a list of strings")
    if not isinstance(pick_ids, list) or not all(isinstance(x, str) for x in pick_ids):
        raise RequestValidationError(
            f"{name}.pick_ids must be a list of strings")
    for pid in pick_ids:
        try:
            parse_pick_id(pid)
        except PickIdError as exc:
            raise RequestValidationError(
                f"{name}.pick_ids: invalid pick_id {pid!r} ({exc})",
            ) from exc
    is_tanking = raw.get("is_tanking", False)
    if not isinstance(is_tanking, bool):
        raise RequestValidationError(f"{name}.is_tanking must be boolean")
    return {
        "roster_id": rid,
        "player_ids": player_ids,
        "pick_ids": pick_ids,
        "is_tanking": is_tanking,
    }


def _parse_ktc(raw: Any) -> KTCConfig:
    if raw is None:
        return dict(_DEFAULT_KTC)
    if not isinstance(raw, dict):
        raise RequestValidationError("ktc must be an object")
    fmt = raw.get("league_format", _DEFAULT_KTC["league_format"])
    if fmt not in _VALID_FORMATS:
        raise RequestValidationError(f"Invalid league_format: {fmt!r}")
    is_redraft = raw.get("is_redraft", _DEFAULT_KTC["is_redraft"])
    if not isinstance(is_redraft, bool):
        raise RequestValidationError("ktc.is_redraft must be boolean")
    tep = raw.get("tep_level", _DEFAULT_KTC["tep_level"])
    if tep not in _VALID_TEP:
        raise RequestValidationError(f"Invalid tep_level: {tep!r}")
    return {"league_format": fmt, "is_redraft": is_redraft, "tep_level": tep}


def parse_trade_request(body: Any) -> TradeRequest:
    if not isinstance(body, dict):
        raise RequestValidationError("Request body must be a JSON object")

    league_id = str(_require(body, "league_id"))
    season = str(_require(body, "season"))
    if len(season) != 4 or not season.isdigit():
        raise RequestValidationError("season must be a four-digit year string")

    side_a = _parse_side("side_a", _require(body, "side_a"))
    side_b = _parse_side("side_b", _require(body, "side_b"))

    if not (side_a["player_ids"] or side_a["pick_ids"]) or not (
        side_b["player_ids"] or side_b["pick_ids"]
    ):
        raise RequestValidationError(
            "Each side must include at least one asset (player_id or pick_id)"
        )

    ktc = _parse_ktc(body.get("ktc"))

    additional_context = body.get("additional_context")
    if additional_context is not None and not isinstance(additional_context, str):
        raise RequestValidationError("additional_context must be a string")

    provider_raw = body.get("provider")
    provider: str | None
    if provider_raw is None:
        provider = None
    elif not isinstance(provider_raw, str):
        raise RequestValidationError("provider must be a string")
    else:
        p = provider_raw.strip().lower()
        if not p:
            raise RequestValidationError("provider must not be empty when set")
        if p not in _KNOWN_PROVIDERS:
            raise RequestValidationError(
                f"Unknown provider {p!r}; expected one of {sorted(_KNOWN_PROVIDERS)}")
        provider = p

    model = body.get("model")
    if model is not None and not isinstance(model, str):
        raise RequestValidationError("model must be a string")

    return {
        "league_id": league_id, "season": season, "ktc": ktc,
        "side_a": side_a, "side_b": side_b,
        "additional_context": additional_context,
        "provider": provider,
        "model": model,
    }
