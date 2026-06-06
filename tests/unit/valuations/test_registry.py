# tests/unit/valuations/test_registry.py
import pytest
from services.valuations.base import ValuationSource, SourceMeta, ValuationRow, SourceUnavailable
from services.valuations import registry


class _Fake(ValuationSource):
    meta = SourceMeta(key="fake", display_name="Fake", kind="trade_value")

    def fetch(self, *, season, league_format, league_settings):
        return [ValuationRow(source_key="fake", external_id="1", name="A",
                             position="QB", team="SF", metric_key="value",
                             metric_value=1.0, rank=1)]

    def health(self):
        return (True, "ok")


def test_register_and_get():
    registry.register("fake", _Fake)
    assert "fake" in registry.known_sources()
    src = registry.get_source("fake")
    rows = src.fetch(season="2026", league_format="superflex", league_settings={})
    assert rows[0].metric_value == 1.0


def test_unknown_source_raises():
    with pytest.raises(SourceUnavailable):
        registry.get_source("nope")
