"""Contract tests: real route responses must validate against web.schemas models.

The dashboard/players-all routes return pre-serialized ``Response`` bytes (their
``response_model`` is docs-only), so these tests are the enforcement mechanism for
the OpenAPI schema: if a serializer grows/renames a field without the matching
schema change, ``extra="forbid"`` makes the relevant test fail here.

Each test drives the endpoint far enough to reach the hand-built serializer with a
populated payload, then validates the parsed JSON against the Pydantic model.
"""
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import patch

from models.entities import (
    Player,
    PlayerInjuryReport,
    PlayerKTCSuperflexValues,
    PlayerNews,
    ValueSnapshot,
)
from models.extensions import db
from web.schemas import (
    DashboardLeagueResponse,
    KtcRefreshAccepted,
    KtcRefreshJobStatus,
    PlayersAllResponse,
)


# --- helpers copied from tests/api/dashboard/test_dashboard_league.py so the
# --- dashboard row exercises the full _player_to_dashboard_dict serialization.
def _fake_ktc_values():
    """SimpleNamespace mimicking PlayerKTCSuperflexValues attribute access."""
    return SimpleNamespace(
        value=8000, rank=10, positional_rank=2,
        overall_tier=1, positional_tier=1,
        tep_value=8200, tep_rank=8, tep_positional_rank=1,
        tep_overall_tier=1, tep_positional_tier=1,
        tepp_value=8300, tepp_rank=7, tepp_positional_rank=1,
        tepp_overall_tier=1, tepp_positional_tier=1,
        teppp_value=8400, teppp_rank=6, teppp_positional_rank=1,
        teppp_overall_tier=1, teppp_positional_tier=1,
    )


def _fake_player(*, oneqb=None, superflex=None, **overrides):
    base = dict(
        id=42, player_name="Justin Jefferson", position="WR", team="MIN",
        sleeper_player_id="6794", full_name="Justin Jefferson",
        last_updated=None, injury_status=None, status="Active",
        birth_date=None, height="6'1\"", weight="195", college="LSU",
        years_exp=5, number=18, age=25.5,
        oneqb_values=oneqb, superflex_values=superflex,
        pickRound=None, pickNum=None, isTrending=True,
        draftYear=2020, byeWeek=6, injury=None,
        injury_body_part=None, injury_notes=None, injury_start_date=None,
        practice_participation=None, practice_description=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _seed_one_superflex_player() -> Player:
    """Persist a real Player + superflex KTC row (+ value snapshots) so
    /api/players/all serializes a populated dashboard row from the ORM."""
    p = Player(
        player_name="Justin Jefferson", position="WR", team="MIN",
        sleeper_player_id="6794", match_key="justinjefferson-WR",
        last_updated=datetime.now(UTC),
    )
    db.session.add(p)
    db.session.flush()
    db.session.add(PlayerKTCSuperflexValues(
        player_id=p.id, is_redraft=False, value=8500, rank=2,
        positional_rank=1, overall_tier=1, positional_tier=1,
        tep_value=8600, tep_rank=1,
    ))
    # Value snapshots populate the `values` block (consensus + sources + projection),
    # exercising SourceValue / ProjectionBlock against the real serializer.
    db.session.add(ValueSnapshot(
        player_id=p.id, source_key="ktc", league_format="superflex",
        metric_key="value", metric_value=8500.0, rank=2, as_of=datetime.now(UTC),
    ))
    db.session.add(ValueSnapshot(
        player_id=p.id, source_key="fantasycalc", league_format="superflex",
        metric_key="value", metric_value=8200.0, rank=3, as_of=datetime.now(UTC),
    ))
    db.session.add(ValueSnapshot(
        player_id=p.id, source_key="sleeper_proj", league_format="superflex",
        metric_key="proj_ros", metric_value=210.5, as_of=datetime.now(UTC),
    ))
    db.session.commit()
    return p


def test_dashboard_league_bundle_matches_schema(client):
    fake_values = _fake_ktc_values()
    fake_player = _fake_player(superflex=fake_values)  # id=42
    # Seed news + an injury report keyed to the fake player's id so the real
    # latest_player_news()/latest_injury_reports() loaders populate those blocks,
    # validating the NewsItem/InjuryReport shapes (not just the empty defaults).
    db.session.add(PlayerNews(
        player_id=42, source="tank01", headline="Jefferson listed as questionable",
        url="https://example.com/jj", image_url="https://example.com/jj.jpg",
        published_at=datetime.now(UTC),
    ))
    db.session.add(PlayerInjuryReport(
        player_id=42, source="nflverse", season="2026", week=1,
        report_status="Questionable", report_primary_injury="Hamstring",
        practice_status="Limited",
    ))
    db.session.commit()
    with patch("routes.dashboard_league.DatabaseManager.get_league_season_only",
               return_value=(True, "2026")), \
         patch("routes.dashboard_league.DatabaseManager.get_league_data",
               return_value={"status": "success",
                             "league": {"league_id": "L1", "season": "2026",
                                        "name": "T", "status": "in_season"},
                             "rosters": [{"roster_id": 1, "owner_id": "u1",
                                          "players": ["6794"], "starters": ["6794"],
                                          "reserve": [], "taxi": [], "settings": {}}],
                             "users": [{"user_id": "u1", "display_name": "A"}]}), \
         patch("managers.database_manager.DatabaseManager.get_players_for_sleeper_ids",
               return_value=([fake_player], None)), \
         patch("routes.dashboard_league._load_ownership_and_meta",
               return_value=({}, {"season": "2026", "week": None,
                                  "league_type": 2, "last_updated": None})), \
         patch("routes.dashboard_league._load_player_stats", return_value={}), \
         patch("managers.sleeper_picks.compute_owned_picks",
               return_value={1: [{"season": "2027", "round": 1, "original_roster_id": 1,
                                  "slot_bucket": "mid", "pick_id": "2027-r1-mid",
                                  "ktc_value": None}]}):
        r = client.get("/api/dashboard/league/L1?season=2026&league_format=superflex"
                       "&is_redraft=false&tep_level=tep")
    assert r.status_code == 200, r.text
    parsed = DashboardLeagueResponse.model_validate(r.json())
    assert parsed.data.players, "contract test must exercise a populated player row"
    assert parsed.data.picks_by_roster, "contract test must exercise a populated pick"
    player = parsed.data.players[0]
    assert player.news, "contract test must exercise a populated news item"
    assert player.injury_report is not None, "contract test must exercise an injury report"


def test_players_all_matches_schema(client):
    _seed_one_superflex_player()
    r = client.get("/api/players/all?league_format=superflex&is_redraft=false")
    assert r.status_code == 200, r.text
    parsed = PlayersAllResponse.model_validate(r.json())
    assert parsed.players, "contract test must exercise a populated player row"


def test_ktc_refresh_202_matches_schema(client):
    with patch("routes.ktc.rankings.ktc_refresh_rate_limited", return_value=None), \
         patch("routes.ktc.rankings.DatabaseManager.verify_database_connection",
               return_value=True), \
         patch("routes.ktc.rankings.try_begin_async_job",
               return_value=("11111111-1111-1111-1111-111111111111", False)):
        r = client.post("/api/ktc/refresh?league_format=superflex&is_redraft=false")
    assert r.status_code == 202, r.text
    KtcRefreshAccepted.model_validate(r.json())


def test_ktc_refresh_status_matches_schema(client):
    rec = {"job_id": "j1", "status": "succeeded", "created_at": "2026-07-16T00:00:00Z",
           "finished_at": "2026-07-16T00:01:00Z", "league_format": "superflex",
           "is_redraft": False, "tep_level": "tep", "error": None,
           "summary": {"players_count": 500, "database_saved_count": 500,
                       "file_saved": False, "s3_uploaded": False},
           "http_status": 200}
    with patch("routes.ktc.rankings.get_refresh_job", return_value=rec):
        r = client.get("/api/ktc/refresh/status/j1")
    assert r.status_code == 200, r.text
    KtcRefreshJobStatus.model_validate(r.json())


def test_openapi_exposes_contract_schemas(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("DashboardLeagueResponse", "PlayersAllResponse",
                 "KtcRefreshAccepted", "KtcRefreshJobStatus"):
        assert name in schemas
