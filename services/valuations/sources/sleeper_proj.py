# services/valuations/sources/sleeper_proj.py
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, UTC
from typing import Any, Optional
import requests
from scrapers.sleeper_scraper import SleeperScraper
from services.valuations.base import ValuationSource, SourceMeta, ValuationRow, SourceUnavailable

_BASE = "https://api.sleeper.com/projections/nfl"
_LAST_REGULAR_WEEK = 18
# Cuts each weekly payload ~5.7MB -> ~2MB by dropping IDP-only rows.
_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


def resolve_current_week(league_settings: dict[str, Any]) -> int:
    """Week to project from: league setting, else Sleeper's NFL state (never a silent week-1 default)."""
    if league_settings.get("current_week"):
        return int(league_settings["current_week"])
    state = SleeperScraper.fetch_nfl_state()
    if not state:
        raise SourceUnavailable("Sleeper projections skipped: NFL state unavailable")
    season_type = state.get("season_type")
    if season_type == "regular":
        return max(1, int(state.get("week") or 1))
    if season_type == "post":
        return _LAST_REGULAR_WEEK + 1
    return 1


def _pts_by_player(payload: Optional[list]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in payload or []:
        pid = str(item.get("player_id") or "")
        pts = (item.get("stats") or {}).get("pts_ppr")
        if pid and pts is not None:
            out[pid] = float(pts)
    return out


class SleeperProjectionsSource(ValuationSource):
    """Sleeper PPR projections: ``proj_week`` (current week) and ``proj_ros`` (current week → 18 summed)."""

    meta = SourceMeta(
        key="sleeper_proj",
        display_name="Sleeper proj",
        kind="projection",
        attribution_url="https://sleeper.com/",
    )

    def _fetch_week(self, season: str, week: int) -> dict[str, float]:
        try:
            resp = requests.get(f"{_BASE}/{season}/{week}",
                                params={"season_type": "regular", "position[]": list(_POSITIONS)},
                                timeout=60)
            resp.raise_for_status()
            return _pts_by_player(resp.json())
        except (requests.RequestException, ValueError) as exc:
            raise SourceUnavailable(f"Sleeper projections fetch failed (week {week}): {exc}") from exc

    def fetch(self, *, season, league_format, league_settings) -> list[ValuationRow]:
        week = resolve_current_week(league_settings)
        if week > _LAST_REGULAR_WEEK:
            return []
        weekly = [self._fetch_week(season, w) for w in range(week, _LAST_REGULAR_WEEK + 1)]

        ros: dict[str, float] = defaultdict(float)
        for pts in weekly:
            for pid, p in pts.items():
                ros[pid] += p

        now = datetime.now(UTC)

        def row(pid: str, metric_key: str, value: float) -> ValuationRow:
            return ValuationRow(
                source_key=self.meta.key, external_id=pid, name="", position="",
                team=None, metric_key=metric_key, metric_value=value,
                rank=None, sleeper_id=pid, as_of=now,
            )

        rows = [row(pid, "proj_week", pts) for pid, pts in weekly[0].items()]
        rows += [row(pid, "proj_ros", round(total, 2)) for pid, total in ros.items()]
        return rows

    def health(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{_BASE}/2026/1", params={"season_type": "regular"}, timeout=15)
            return (r.ok, f"HTTP {r.status_code}")
        except requests.RequestException as exc:
            return (False, str(exc))
