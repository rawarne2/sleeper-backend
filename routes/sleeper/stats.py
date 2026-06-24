from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from managers.database_manager import DatabaseManager
from models.entities import SleeperLeague, SleeperLeagueStats
from models.extensions import db
from services.daily_refresh import refresh_weekly_stats_for_league
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging
from web.errors import ApiError

router = APIRouter(prefix="/api/sleeper/league", tags=["Sleeper Weekly Stats"])
logger = setup_logging()


class StatsSeedBody(BaseModel):
    league_name: Optional[str] = None
    season: Optional[str] = None
    league_type: Optional[str] = None
    scoring_settings: Optional[str] = None


@router.post("/{league_id}/stats/seed", operation_id="seed_league_stats_post",
             summary="Seed league stats information")
@router.put("/{league_id}/stats/seed", operation_id="seed_league_stats_put",
            summary="Seed league stats information")
def seed_league_stats(league_id: str, body: Optional[StatsSeedBody] = None):
    """
    Seed or update league information needed for weekly stats functionality.
    This endpoint should be called once per league before fetching weekly stats.
    """
    data = body.model_dump(exclude_none=False) if body else {}
    league_name = data.get('league_name')
    season = data.get('season')
    league_type = data.get('league_type')
    scoring_settings = data.get('scoring_settings')

    existing = db.session.execute(select(SleeperLeagueStats).filter_by(league_id=league_id)).scalars().first()

    if existing:
        league_name = league_name or existing.league_name
        season = season or existing.season
        league_type = league_type or existing.league_type or 'dynasty'
    else:
        if not league_name or not season:
            raise ApiError(
                'league_name and season are required for new leagues',
                400,
            )
        league_type = league_type or 'dynasty'

    logger.info("Seeding league stats for league: %s, season: %s, type: %s",
                league_id, season, league_type)

    result = DatabaseManager.seed_league_stats(
        league_id=league_id,
        league_name=league_name,
        season=season,
        league_type=league_type,
        scoring_settings=scoring_settings
    )

    if result.get('status') == 'error':
        raise ApiError(
            'Failed to seed league stats',
            500,
            details=result.get('error', 'Unknown error'),
        )

    row = db.session.execute(select(SleeperLeagueStats).filter_by(league_id=league_id)).scalars().first()
    start_week = (row.last_week_updated or 0) + 1 if row else 1
    weeks_to_fetch = range(start_week, 19)

    weekly_summary = None
    if start_week <= 18:
        logger.info(
            "Auto-fetching weekly stats league=%s weeks=%s-18",
            league_id, start_week,
        )
        weekly_summary = refresh_weekly_stats_for_league(
            league_id, season, weeks=weeks_to_fetch, league_type=league_type,
        )

    refreshed_row = db.session.execute(select(SleeperLeagueStats).filter_by(league_id=league_id)).scalars().first()
    last_week = refreshed_row.last_week_updated if refreshed_row else 0

    return {
        'status': 'success',
        'message': 'League stats seeded successfully',
        'action': result.get('action'),
        'league_id': league_id,
        'league_name': league_name,
        'season': season,
        'last_week_updated': last_week,
        'weekly_stats': weekly_summary,
        'timestamp': utc_now_rfc3339(),
    }


@router.get("/{league_id}/stats/week/{week}", summary="Get weekly stats for a specific week")
def get_weekly_stats(
    league_id: str,
    week: int,
    season: str = Query("2024"),
    league_type: str = Query("dynasty"),
    average: str = Query("false"),
):
    """
    Get weekly fantasy points and roster information for all players in a specific week.
    Returns player scoring data including points, roster ID, and starter status.
    """
    if not 1 <= week <= 18:
        raise ApiError('week must be between 1 and 18', 400)

    use_average = average.lower() == 'true'

    logger.info("Weekly stats requested for league: %s, week: %s, season: %s, average: %s",
                league_id, week, season, use_average)

    stats_result = DatabaseManager.get_weekly_stats(
        season=season,
        week=week if not use_average else None,
        league_type=league_type,
        average=use_average
    )

    if stats_result.get('status') == 'error':
        raise ApiError(
            'Failed to retrieve weekly stats',
            500,
            details=stats_result.get('error', 'Unknown error'),
        )

    return {
        **stats_result,
        'timestamp': utc_now_rfc3339(),
    }


@router.post("/{league_id}/stats/week/{week}", operation_id="refresh_weekly_stats_post",
             summary="Refresh/Update weekly stats for a specific week")
@router.put("/{league_id}/stats/week/{week}", operation_id="refresh_weekly_stats_put",
            summary="Refresh/Update weekly stats for a specific week")
def refresh_weekly_stats(
    league_id: str,
    week: int,
    season: Optional[str] = Query(None),
    league_type: Optional[str] = Query(None),
):
    """
    Fetch fresh weekly stats data from Sleeper API for a specific week and save to database.
    This endpoint fetches matchup data and extracts player scoring information.
    """
    if not 1 <= week <= 18:
        raise ApiError('week must be between 1 and 18', 400)

    if not season or not league_type:
        existing = db.session.execute(select(SleeperLeagueStats).filter_by(league_id=league_id)).scalars().first()
        if existing:
            season = season or existing.season
            league_type = league_type or existing.league_type or 'dynasty'
        else:
            league_row = db.session.execute(select(SleeperLeague).filter_by(league_id=league_id)).scalars().first()
            season = season or (str(league_row.season) if league_row and league_row.season else None)
            league_type = league_type or 'dynasty'

    if not season:
        raise ApiError(
            'season is required (not found in DB for this league_id)',
            400,
        )

    logger.info("Weekly stats refresh requested for league: %s, week: %s, season: %s",
                league_id, week, season)

    summary = refresh_weekly_stats_for_league(
        league_id, season, weeks=[week], league_type=league_type,
    )
    week_results = summary.get('weeks') or []
    week_entry = week_results[0] if week_results else {}
    errors = summary.get('errors') or []

    if errors:
        raise ApiError(
            'Failed to refresh weekly stats',
            500,
            details=errors[0].get('error', 'Unknown error'),
        )

    if week_entry.get('status') == 'no_data':
        raise ApiError(
            'Failed to fetch weekly matchups',
            400,
            details='No matchup data returned from Sleeper API',
        )

    if week_entry.get('status') == 'no_records':
        raise ApiError(
            'Failed to parse weekly matchups',
            400,
            details='No player scoring records found in matchup data',
        )

    refreshed_row = db.session.execute(select(SleeperLeagueStats).filter_by(league_id=league_id)).scalars().first()
    last_week = refreshed_row.last_week_updated if refreshed_row else None

    return {
        'status': 'success',
        'message': 'Weekly stats refreshed successfully',
        'league_id': league_id,
        'week': week,
        'season': season,
        'league_type': league_type,
        'last_week_updated': last_week,
        'refresh_results': week_entry,
        'timestamp': utc_now_rfc3339(),
    }
