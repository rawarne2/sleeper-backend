import json
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query

from cache.redis_dashboard import invalidate_dashboard_league_caches_for_ktc_dimensions
from models.entities import SleeperLeague, SleeperWeeklyData
from models.extensions import db
from scrapers.sleeper_scraper import SleeperScraper
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging
from web.errors import ApiError

router = APIRouter(prefix="/api/sleeper/players", tags=["Sleeper Research"])
logger = setup_logging()

_RESEARCH_LEAGUE_TYPES = frozenset({'dynasty', 'redraft'})


def _season_path_error(season: str) -> Optional[str]:
    s = season.strip()
    if len(s) != 4 or not s.isdigit():
        return 'season path must be a four-digit NFL year'
    return None


def _normalize_league_type(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    v = (raw or 'dynasty').strip().lower()
    if v not in _RESEARCH_LEAGUE_TYPES:
        return None, "league_type must be 'dynasty' or 'redraft'"
    return v, None


def _parse_week_param(value: Optional[str]) -> Tuple[Optional[int], bool, Optional[str]]:
    """Parse ?week=... where 'all' means weeks 1..18."""
    raw = (value or '1').strip().lower()
    if raw == 'all':
        return None, True, None
    try:
        week = int(raw)
    except (TypeError, ValueError):
        return None, False, "week must be an integer or 'all'"
    if week < 1 or week > 18:
        return None, False, "week must be between 1 and 18, or 'all'"
    return week, False, None


def _current_research_season() -> str:
    """Latest league season in DB, or the current calendar year as a fallback."""
    row = (
        db.session.query(db.func.max(SleeperLeague.season)).scalar()
    )
    if row and len(str(row)) == 4 and str(row).isdigit():
        return str(row)
    return str(datetime.now(UTC).year)


def research_weeks_to_persist(
    season: str,
    *,
    week_param: Optional[int],
    fetch_all_weeks: bool,
    current_season: str,
) -> Tuple[List[int], bool]:
    """Resolve which weeks to refresh and whether the request was truncated.

    Current season honors ``week=all`` / single week as requested. Prior seasons
    collapse to week 18 only — dynasty consumers just need the season-ending
    snapshot, and refreshing 18 weeks of API calls per old season is wasteful.
    """
    if season == current_season:
        if fetch_all_weeks:
            return list(range(1, 19)), False
        return [int(week_param) if week_param else 1], False

    if fetch_all_weeks:
        return [18], True
    requested = int(week_param) if week_param else 1
    if requested == 18:
        return [18], False
    return [18], True


def _upsert_research_rows(
    season: str,
    week: int,
    league_type: str,
    raw_rd: Dict[str, Any],
) -> Dict[str, Any]:
    """Upsert ``research_data`` for one ``(season, week, league_type)`` slice.

    Never deletes the week up front — rows with matchup ``points`` / ``is_starter``
    / ``roster_id`` must coexist with research data on the same unique key.
    """
    inserted = 0
    updated = 0
    skipped = 0

    existing = {
        row.player_id: row
        for row in SleeperWeeklyData.query.filter_by(
            season=season,
            week=week,
            league_type=league_type,
        ).all()
    }

    now = datetime.now(UTC)
    for player_id, player_data in raw_rd.items():
        try:
            serialized = json.dumps(player_data)
        except (TypeError, ValueError) as e:
            logger.error(
                "Error serializing research record for player %s week=%s: %s",
                player_id,
                week,
                e,
            )
            skipped += 1
            continue

        existing_row = existing.get(str(player_id))
        if existing_row is not None:
            existing_row.research_data = serialized
            existing_row.last_updated = now
            updated += 1
        else:
            new_record = SleeperWeeklyData(
                season=season,
                week=week,
                league_type=league_type,
                player_id=str(player_id),
                research_data=serialized,
            )
            db.session.add(new_record)
            inserted += 1

    db.session.commit()
    return {
        'inserted': inserted,
        'updated': updated,
        'skipped': skipped,
        'saved_count': inserted + updated,
    }


def _refresh_research_for_week(season: str, week: int, league_type: str) -> Dict[str, Any]:
    """Fetch + upsert one week of research; matchup-derived columns are preserved."""
    research_data = SleeperScraper.scrape_research_data(season, week, league_type)
    if not research_data.get('success'):
        return {
            'status': 'error',
            'week': week,
            'error': research_data.get('error', 'Unknown error'),
        }

    raw_rd = research_data.get('research_data')
    if not isinstance(raw_rd, dict):
        return {
            'status': 'error',
            'week': week,
            'error': f"Unexpected research payload shape: {type(raw_rd).__name__}",
        }

    counts = _upsert_research_rows(season, week, league_type, raw_rd)
    return {
        'status': 'success',
        'week': week,
        'saved_count': counts['saved_count'],
        'inserted': counts['inserted'],
        'updated': counts['updated'],
        'skipped': counts['skipped'],
        'total_players': len(raw_rd),
    }


@router.get("/research/{season}", summary="Get player research data")
def get_research_data(
    season: str,
    week: str | None = Query(None),
    league_type: str | None = Query(None),
):
    """
    Get player research data for a specific season. Returns comprehensive research metrics
    including rankings, projections, performance data, and statistical analysis.
    Checks database first.
    """
    week_val, fetch_all_weeks, week_error = _parse_week_param(week)
    if week_error:
        raise ApiError(week_error, 400, season=season)

    sea_err = _season_path_error(season)
    if sea_err:
        raise ApiError(sea_err, 400, season=season.strip())

    league_type_val, lt_err = _normalize_league_type(league_type)
    if lt_err:
        raise ApiError(lt_err, 400, season=season)

    logger.info(
        "Research data requested for season: %s, week: %s", season, 'all' if fetch_all_weeks else week_val)

    # Check database first
    query = SleeperWeeklyData.query.filter_by(
        season=season,
        league_type=league_type_val
    )
    if fetch_all_weeks:
        query = query.filter(SleeperWeeklyData.week.between(1, 18))
    else:
        query = query.filter_by(week=week_val)
    research_records = query.all()

    if research_records:
        logger.info("Found %s research records in database",
                    len(research_records))
        return {
            'status': 'success',
            'data': [record.to_dict() for record in research_records],
            'week': 'all' if fetch_all_weeks else week_val,
            'source': 'database',
            'database_saved': True,
            'timestamp': utc_now_rfc3339(),
        }

    if fetch_all_weeks:
        raise ApiError(
            'No research data found for weeks 1-18',
            404,
            details=(
                'Run PUT /api/sleeper/players/research/{season}?week=all first'
            ),
            season=season,
        )

    # If not in database, try to fetch from Sleeper API
    logger.info(
        "No research data found in database, fetching from Sleeper API...")
    research_data = SleeperScraper.scrape_research_data(
        season, week_val, league_type_val)

    if not research_data.get('success'):
        raise ApiError(
            'Failed to fetch research data',
            404,
            details=research_data.get('error', 'Unknown error'),
            season=season,
        )

    return {
        'status': 'success',
        'data': research_data.get('research_data', []),
        'source': 'sleeper_api',
        'database_saved': False,
        'timestamp': utc_now_rfc3339(),
    }


@router.api_route("/research/{season}", methods=["POST", "PUT"], summary="Refresh/Update research data")
def refresh_research_data(
    season: str,
    week: str | None = Query(None),
    league_type: str | None = Query(None),
):
    """
    Refresh research data from Sleeper API for a specific season.
    ``week=all`` refreshes weeks 1–18; ``week=<n>`` refreshes a single week.
    """
    week_val, refresh_all_weeks, week_error = _parse_week_param(week)
    if week_error:
        raise ApiError(week_error, 400, season=season)

    sea_err = _season_path_error(season)
    if sea_err:
        raise ApiError(sea_err, 400, season=season.strip())

    league_type_val, lt_err = _normalize_league_type(league_type)
    if lt_err:
        raise ApiError(lt_err, 400, season=season)

    logger.info(
        "Manual refresh requested for research data: season=%s, week=%s",
        season,
        'all' if refresh_all_weeks else week_val,
    )

    current_season = _current_research_season()
    weeks, truncated = research_weeks_to_persist(
        season,
        week_param=week_val,
        fetch_all_weeks=refresh_all_weeks,
        current_season=current_season,
    )
    if truncated:
        logger.info(
            "Prior-season research request truncated season=%s requested=%s -> weeks=%s",
            season,
            'all' if refresh_all_weeks else week_val,
            weeks,
        )

    per_week: List[Dict[str, Any]] = []
    total_saved = 0
    failed = 0
    first_error: Optional[str] = None

    for wk in weeks:
        res = _refresh_research_for_week(season, wk, league_type_val)
        per_week.append(res)
        if res.get('status') == 'success':
            total_saved += int(res.get('saved_count', 0))
        else:
            failed += 1
            if first_error is None:
                first_error = str(res.get('error', 'Unknown error'))

    invalidate_dashboard_league_caches_for_ktc_dimensions(None, None, None)

    if failed == len(weeks):
        raise ApiError(
            'Failed to refresh research data',
            400,
            details=first_error or 'Unknown error',
            season=season,
            week='all' if refresh_all_weeks else week_val,
            league_type=league_type_val,
        )

    return {
        'status': 'success',
        'message': 'Research data refreshed successfully',
        'season': season,
        'week': 'all' if refresh_all_weeks else week_val,
        'league_type': league_type_val,
        'refresh_results': {
            'saved_count': total_saved,
            'weeks_attempted': len(weeks),
            'weeks_failed': failed,
            'weeks': per_week,
            'retention_applied': 'prior-season-week-18' if truncated else 'requested',
        },
        'source': 'database',
        'database_saved': True,
        'timestamp': utc_now_rfc3339(),
    }
