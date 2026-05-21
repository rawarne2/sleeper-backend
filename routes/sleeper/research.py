import json
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from cache.redis_dashboard import invalidate_dashboard_league_caches_for_ktc_dimensions
from models.entities import SleeperLeague, SleeperWeeklyData
from models.extensions import db
from routes.helpers import json_api_error, with_error_handling
from scrapers.sleeper_scraper import SleeperScraper
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging

sleeper_research_bp = Blueprint(
    'sleeper_research', __name__, url_prefix='/api/sleeper/players')
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


@sleeper_research_bp.route('/research/<string:season>', methods=['GET'])
@with_error_handling
def get_research_data(season: str):
    """
    Get player research data
    ---
    tags:
      - Sleeper Research
    summary: Get player research data
    description: |
      Get player research data for a specific season. Returns comprehensive research metrics including rankings, projections, performance data, and statistical analysis. Checks database first.
    parameters:
      - name: season
        in: path
        description: The NFL season year
        required: true
        type: string
        pattern: '^[0-9]{4}$'
      - name: week
        in: query
        description: Week number (1-18 for regular season)
        required: false
        type: integer
        minimum: 1
        maximum: 18
        default: 1
      - name: league_type
        in: query
        description: League type
        required: false
        type: string
        enum: ['dynasty', 'redraft']
        default: 'dynasty'
    responses:
      200:
        description: Research data retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            data:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  season:
                    type: string
                  week:
                    type: integer
                  league_type:
                    type: string
                    enum: ['dynasty', 'redraft']
                  player_id:
                    type: string
                  research_data:
                    type: object
                    description: Research metrics and analytics data
                  last_updated:
                    type: string
                    format: date-time
            source:
              type: string
              enum: ['database', 'sleeper_api']
            database_saved:
              type: boolean
            timestamp:
              type: string
              format: date-time
      400:
        description: Invalid week, season path, or league_type query
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            timestamp:
              type: string
              format: date-time
      404:
        description: Research data not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to fetch research data'
            details:
              type: string
            season:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
    """
    week, fetch_all_weeks, week_error = _parse_week_param(request.args.get('week'))
    if week_error:
        return json_api_error(week_error, 400, season=season)

    sea_err = _season_path_error(season)
    if sea_err:
        return json_api_error(sea_err, 400, season=season.strip())

    league_type, lt_err = _normalize_league_type(
        request.args.get('league_type'))
    if lt_err:
        return json_api_error(lt_err, 400, season=season)

    logger.info(
        "Research data requested for season: %s, week: %s", season, 'all' if fetch_all_weeks else week)

    # Check database first
    query = SleeperWeeklyData.query.filter_by(
        season=season,
        league_type=league_type
    )
    if fetch_all_weeks:
        query = query.filter(SleeperWeeklyData.week.between(1, 18))
    else:
        query = query.filter_by(week=week)
    research_records = query.all()

    if research_records:
        logger.info("Found %s research records in database",
                    len(research_records))
        return jsonify({
            'status': 'success',
            'data': [record.to_dict() for record in research_records],
            'week': 'all' if fetch_all_weeks else week,
            'source': 'database',
            'database_saved': True,
            'timestamp': utc_now_rfc3339(),
        })

    if fetch_all_weeks:
        return json_api_error(
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
        season, week, league_type)

    if not research_data.get('success'):
        return json_api_error(
            'Failed to fetch research data',
            404,
            details=research_data.get('error', 'Unknown error'),
            season=season,
        )

    return jsonify({
        'status': 'success',
        'data': research_data.get('research_data', []),
        'source': 'sleeper_api',
        'database_saved': False,
        'timestamp': utc_now_rfc3339(),
    })


@sleeper_research_bp.route('/research/<string:season>', methods=['POST', 'PUT'])
@with_error_handling
def refresh_research_data(season: str):
    """
    Refresh/Update research data
    ---
    tags:
      - Sleeper Research
    summary: Refresh/Update research data
    description: Refresh research data from Sleeper API for a specific season.
    parameters:
      - name: season
        in: path
        description: The NFL season year
        required: true
        type: string
        pattern: '^[0-9]{4}$'
      - name: week
        in: query
        description: Week number (1-18 for regular season)
        required: false
        type: integer
        minimum: 1
        maximum: 18
        default: 1
      - name: league_type
        in: query
        description: League type
        required: false
        type: string
        enum: ['dynasty', 'redraft']
        default: 'dynasty'
    responses:
      200:
        description: Research data refreshed successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            message:
              type: string
              example: 'Research data refreshed successfully'
            season:
              type: string
            week:
              type: integer
            league_type:
              type: string
              enum: ['dynasty', 'redraft']
            refresh_results:
              type: object
            timestamp:
              type: string
              format: date-time
      400:
        description: Invalid parameters or failed to refresh
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to refresh research data'
            details:
              type: string
            season:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to save refreshed research data'
            details:
              type: string
            season:
              type: string
    """
    week, refresh_all_weeks, week_error = _parse_week_param(request.args.get('week'))
    if week_error:
        return json_api_error(week_error, 400, season=season)

    sea_err = _season_path_error(season)
    if sea_err:
        return json_api_error(sea_err, 400, season=season.strip())

    league_type, lt_err = _normalize_league_type(
        request.args.get('league_type'))
    if lt_err:
        return json_api_error(lt_err, 400, season=season)

    logger.info(
        "Manual refresh requested for research data: season=%s, week=%s",
        season,
        'all' if refresh_all_weeks else week,
    )

    current_season = _current_research_season()
    weeks, truncated = research_weeks_to_persist(
        season,
        week_param=week,
        fetch_all_weeks=refresh_all_weeks,
        current_season=current_season,
    )
    if truncated:
        logger.info(
            "Prior-season research request truncated season=%s requested=%s -> weeks=%s",
            season,
            'all' if refresh_all_weeks else week,
            weeks,
        )

    per_week: List[Dict[str, Any]] = []
    total_saved = 0
    failed = 0
    first_error: Optional[str] = None

    for wk in weeks:
        res = _refresh_research_for_week(season, wk, league_type)
        per_week.append(res)
        if res.get('status') == 'success':
            total_saved += int(res.get('saved_count', 0))
        else:
            failed += 1
            if first_error is None:
                first_error = str(res.get('error', 'Unknown error'))

    invalidate_dashboard_league_caches_for_ktc_dimensions(None, None, None)

    if failed == len(weeks):
        return json_api_error(
            'Failed to refresh research data',
            400,
            details=first_error or 'Unknown error',
            season=season,
            week='all' if refresh_all_weeks else week,
            league_type=league_type,
        )

    return jsonify({
        'status': 'success',
        'message': 'Research data refreshed successfully',
        'season': season,
        'week': 'all' if refresh_all_weeks else week,
        'league_type': league_type,
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
    })
