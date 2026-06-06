# services/valuations/sources/fantasycalc.py
from __future__ import annotations
from datetime import datetime, UTC
from typing import Any
import requests
from services.valuations.base import ValuationSource, SourceMeta, ValuationRow, SourceUnavailable

_API = "https://api.fantasycalc.com/values/current"
_METRICS = {
    "value": "value",
    "redraftValue": "redraft_value",
    "trend30Day": "trend_30day",
    "maybeMovingStandardDeviation": "volatility",
    "maybeTradeFrequency": "trade_frequency",
}


def _num_qbs(league_settings: dict[str, Any]) -> int:
    positions = league_settings.get("roster_positions") or []
    return 2 if "SUPER_FLEX" in positions else 1


def _ppr(league_settings: dict[str, Any]) -> float:
    scoring = league_settings.get("scoring_settings") or {}
    try:
        return float(scoring.get("rec", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _num_teams(league_settings: dict[str, Any]) -> int:
    try:
        return int(league_settings.get("total_rosters") or 12)
    except (TypeError, ValueError):
        return 12


class FantasyCalcSource(ValuationSource):
    meta = SourceMeta(
        key="fantasycalc",
        display_name="FantasyCalc",
        kind="trade_value",
        attribution_url="https://fantasycalc.com/",
    )

    def fetch(self, *, season, league_format, league_settings) -> list[ValuationRow]:
        params = {
            "isDynasty": "true",
            "numQbs": 2 if league_format == "superflex" else _num_qbs(league_settings),
            "numTeams": _num_teams(league_settings),
            "ppr": _ppr(league_settings),
        }
        try:
            resp = requests.get(_API, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise SourceUnavailable(f"FantasyCalc fetch failed: {exc}") from exc

        now = datetime.now(UTC)
        rows: list[ValuationRow] = []
        for item in data:
            p = item.get("player") or {}
            ext_id = str(p.get("id"))
            name = p.get("name") or ""
            position = p.get("position") or ""
            team = p.get("maybeTeam")
            sleeper_id = str(p["sleeperId"]) if p.get("sleeperId") else None
            for api_key, metric_key in _METRICS.items():
                if item.get(api_key) is None:
                    continue
                rows.append(ValuationRow(
                    source_key=self.meta.key, external_id=ext_id, name=name,
                    position=position, team=team, metric_key=metric_key,
                    metric_value=float(item[api_key]),
                    rank=item.get("overallRank") if metric_key == "value" else None,
                    sleeper_id=sleeper_id,
                    as_of=now, raw=item if metric_key == "value" else {},
                ))
        return rows

    def health(self) -> tuple[bool, str]:
        try:
            r = requests.get(_API, params={"isDynasty": "true", "numQbs": 1,
                                           "numTeams": 12, "ppr": 1}, timeout=15)
            return (r.ok, f"HTTP {r.status_code}")
        except requests.RequestException as exc:
            return (False, str(exc))
