from __future__ import annotations
from datetime import datetime, UTC
from typing import Any

from scrapers import tank01_client
from services.valuations.base import ValuationSource, SourceMeta, ValuationRow, SourceUnavailable


def _fantasy_points(proj: dict[str, Any]) -> float | None:
    fpd = proj.get("fantasyPointsDefault")
    if isinstance(fpd, dict):
        for key in ("PPR", "halfPPR", "standard"):
            if fpd.get(key) is not None:
                try:
                    return float(fpd[key])
                except (TypeError, ValueError):
                    pass
    raw = proj.get("fantasyPoints")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class Tank01Source(ValuationSource):
    """Tank01 (RapidAPI) weekly fantasy projection. Inactive unless RAPIDAPI_KEY is set."""

    meta = SourceMeta(
        key="tank01",
        display_name="Tank01",
        kind="projection",
        attribution_url="https://tank01.com/",
    )

    def fetch(self, *, season, league_format, league_settings) -> list[ValuationRow]:
        if not tank01_client.is_configured():
            raise SourceUnavailable("Tank01 skipped: RAPIDAPI_KEY not set")
        week = int(league_settings.get("current_week") or 1)
        try:
            id_map = tank01_client.sleeper_id_by_tank_id()
            projections = tank01_client.get_projections(week)
        except Exception as exc:  # noqa: BLE001 - surfaces as SourceUnavailable to the fail-soft ingest
            raise SourceUnavailable(f"Tank01 projections fetch failed: {exc}") from exc

        now = datetime.now(UTC)
        rows: list[ValuationRow] = []
        for tid, proj in (projections or {}).items():
            if not isinstance(proj, dict):
                continue
            pts = _fantasy_points(proj)
            if pts is None:
                continue
            sleeper_id = id_map.get(str(tid)) or (
                str(proj["sleeperBotID"]) if proj.get("sleeperBotID") else None)
            rows.append(ValuationRow(
                source_key=self.meta.key, external_id=str(tid),
                name=proj.get("longName") or "", position=proj.get("pos") or "",
                team=proj.get("team"), metric_key="tank_proj_week", metric_value=pts,
                sleeper_id=sleeper_id, as_of=now,
            ))
        return rows

    def health(self) -> tuple[bool, str]:
        if not tank01_client.is_configured():
            return (False, "RAPIDAPI_KEY not set")
        try:
            tank01_client.get_projections(1)
            return (True, "OK")
        except Exception as exc:  # noqa: BLE001
            return (False, str(exc))
