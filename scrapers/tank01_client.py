"""Thin client for the Tank01 NFL API (RapidAPI).

Free tier: ~1000 calls/month, so callers should hit this at most a few times a day
(the nightly cron is the natural limiter). Everything is gated on RAPIDAPI_KEY; when
it is unset the client reports not-configured and callers degrade gracefully.

Assumed response shapes (confirm against the RapidAPI dashboard once a key is set):
- getNFLPlayerList -> body: [ {playerID, longName, pos, team, sleeperBotID, espnID, ...} ]
- getNFLProjections -> body: { <playerID>: {fantasyPoints, fantasyPointsDefault:{standard,PPR,halfPPR}, longName, pos, team} }
  (older shape nests the map under body.playerProjections)
- getNFLNews -> body: [ {title, link, image, playerID: ["..."]} ]
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

_DEFAULT_HOST = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
_TIMEOUT = 30


def _host() -> str:
    return (os.getenv("TANK01_RAPIDAPI_HOST") or _DEFAULT_HOST).strip()


def api_key() -> str:
    return (os.getenv("RAPIDAPI_KEY") or "").strip()


def is_configured() -> bool:
    return bool(api_key())


def _headers() -> dict[str, str]:
    return {"x-rapidapi-key": api_key(), "x-rapidapi-host": _host()}


def _get_body(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    """GET a Tank01 endpoint and return its `body` (payloads wrap data under `body`)."""
    resp = requests.get(f"https://{_host()}/{path}", headers=_headers(),
                        params=params or {}, timeout=_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and "body" in payload:
        return payload["body"]
    return payload


def get_player_list() -> list[dict]:
    body = _get_body("getNFLPlayerList")
    return body if isinstance(body, list) else []


def sleeper_id_by_tank_id() -> dict[str, str]:
    """Map Tank01 playerID -> Sleeper player_id (via sleeperBotID) for id resolution."""
    out: dict[str, str] = {}
    for p in get_player_list():
        if not isinstance(p, dict):
            continue
        tid = str(p.get("playerID") or "")
        sid = p.get("sleeperBotID")
        if tid and sid:
            out[tid] = str(sid)
    return out


def get_projections(week: int | str) -> dict:
    body = _get_body("getNFLProjections", {"week": str(week)})
    if isinstance(body, dict):
        inner = body.get("playerProjections")
        if isinstance(inner, dict):
            return inner
        return body
    return {}


def get_news(max_items: int = 50, *, fantasy_news: bool = True) -> list[dict]:
    params = {"fantasyNews": "true" if fantasy_news else "false", "maxItems": str(max_items)}
    body = _get_body("getNFLNews", params)
    return body if isinstance(body, list) else []
