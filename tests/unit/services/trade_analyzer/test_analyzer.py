"""run_analysis provider error mapping."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from data_types.trade_analyzer_types import TradeRequest
from services.trade_analyzer.analyzer import run_analysis
from services.trade_analyzer.providers.base import ProviderRateLimited


def _minimal_req() -> TradeRequest:
    return {
        "league_id": "1210364682523656192",
        "season": "2026",
        "side_a": {"roster_id": 1, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 2, "player_ids": ["4034"], "pick_ids": []},
        "ktc": {"league_format": "sf", "is_redraft": False, "tep_level": ""},
    }


def test_run_analysis_maps_provider_rate_limit_to_429(league_fixture):
    provider = MagicMock()
    provider.generate.side_effect = ProviderRateLimited(
        "Gemini rate limit reached (HTTP 429). Wait a minute and try again.",
        retry_after_seconds=60,
    )
    provider.health_check.return_value = (True, "ok")

    with patch(
        "services.trade_analyzer.analyzer.get_provider",
        return_value=provider,
    ), patch(
        "services.trade_analyzer.analyzer.cached_health_check",
        return_value=(True, "ok"),
    ), patch(
        "services.trade_analyzer.analyzer.load_league_bundle",
        return_value=league_fixture,
    ), patch(
        "services.trade_analyzer.analyzer.build_context",
        return_value={"trade": {"consensus_totals": {}}},
    ):
        outcome = run_analysis(
            _minimal_req(),
            provider_name="gemini",
            model="gemini-2.0-flash",
            timeout_s=60,
        )

    assert outcome.status_code == 429
    assert "429" in outcome.body["error"]
    assert outcome.body["retry_after_seconds"] == 60
    assert outcome.body["provider_used"] == "gemini"
