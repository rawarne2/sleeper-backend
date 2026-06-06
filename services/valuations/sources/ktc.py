# services/valuations/sources/ktc.py
from __future__ import annotations
from datetime import datetime, UTC
from models.entities import Player, PlayerKTCSuperflexValues, PlayerKTCOneQBValues
from services.valuations.base import ValuationSource, SourceMeta, ValuationRow


class KtcSource(ValuationSource):
    """Re-emit already-scraped KTC values from the DB as ValuationRows so KTC
    participates in the blend uniformly. KTC ingestion itself stays owned by the
    existing ktc_scraper pipeline; this only reads current values.
    """
    meta = SourceMeta(
        key="ktc",
        display_name="KeepTradeCut",
        kind="trade_value",
        attribution_url="https://keeptradecut.com/",
    )

    def fetch(self, *, season, league_format, league_settings) -> list[ValuationRow]:
        model = PlayerKTCSuperflexValues if league_format == "superflex" else PlayerKTCOneQBValues
        now = datetime.now(UTC)
        rows: list[ValuationRow] = []
        q = (model.query.filter_by(is_redraft=False)
             .join(Player, Player.id == model.player_id)
             .add_entity(Player))
        for vals, player in q.all():
            if vals.value is None:
                continue
            rows.append(ValuationRow(
                source_key=self.meta.key, external_id=str(player.id),
                name=player.player_name, position=player.position, team=player.team,
                metric_key="value", metric_value=float(vals.value),
                rank=getattr(vals, "rank", None), as_of=now, raw={},
            ))
        return rows

    def health(self) -> tuple[bool, str]:
        return (True, "DB-backed")
