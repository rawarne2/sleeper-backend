# services/valuations/sources/sleeper_proj.py
from __future__ import annotations
from datetime import datetime, UTC
import requests
from services.valuations.base import ValuationSource, SourceMeta, ValuationRow, SourceUnavailable

_BASE = "https://api.sleeper.com/projections/nfl"


class SleeperProjectionsSource(ValuationSource):
    meta = SourceMeta(
        key="sleeper_proj",
        display_name="Sleeper proj",
        kind="projection",
        attribution_url="https://sleeper.com/",
    )

    def fetch(self, *, season, league_format, league_settings) -> list[ValuationRow]:
        week = int(league_settings.get("current_week") or 1)
        url = f"{_BASE}/{season}/{week}"
        try:
            resp = requests.get(url, params={"season_type": "regular"}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise SourceUnavailable(f"Sleeper projections fetch failed: {exc}") from exc

        now = datetime.now(UTC)
        rows: list[ValuationRow] = []
        for item in data or []:
            pid = str(item.get("player_id") or "")
            stats = item.get("stats") or {}
            pts = stats.get("pts_ppr")
            if not pid or pts is None:
                continue
            rows.append(ValuationRow(
                source_key=self.meta.key, external_id=pid, name="", position="",
                team=None, metric_key="proj_week", metric_value=float(pts),
                rank=None, sleeper_id=pid, as_of=now, raw=item,
            ))
        return rows

    def health(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{_BASE}/2026/1", params={"season_type": "regular"}, timeout=15)
            return (r.ok, f"HTTP {r.status_code}")
        except requests.RequestException as exc:
            return (False, str(exc))
