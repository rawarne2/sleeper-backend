"""
Orchestration for daily / scheduled data refresh (KTC + leagues + research + weekly stats).

Kept separate from route handlers so it can be called from Flask or a CLI later.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from cache.redis_dashboard import invalidate_dashboard_league
from managers.database_manager import DatabaseManager
from models.entities import SleeperLeague, SleeperLeagueStats, SleeperWeeklyData
from models.extensions import db
from scrapers.ktc_scraper import KTCScraper
from scrapers.pipelines import scrape_and_save_all_ktc_data
from scrapers.sleeper_scraper import SleeperScraper
from services.types import DailyRefreshSummary
from utils.helpers import setup_logging

logger = setup_logging()

REGULAR_SEASON_WEEKS = range(1, 19)  # Sleeper uses weeks 1..18 for regular season + week 18


def _league_ids_for_refresh() -> List[str]:
    """All leagues persisted in the DB; if none yet, fall back to built-in defaults."""
    rows = SleeperLeague.query.with_entities(SleeperLeague.league_id).all()
    out = [r[0] for r in rows if r and r[0]]
    if out:
        return out
    return [
        "1333945997071515648",
        "1210364682523656192",
        "1050831680350568448",
    ]


def _league_id_to_season() -> Dict[str, str]:
    """Map league_id -> season for all leagues persisted in the DB."""
    rows = SleeperLeague.query.with_entities(
        SleeperLeague.league_id, SleeperLeague.season
    ).all()
    return {r[0]: str(r[1]) for r in rows if r and r[0] and r[1]}


def refresh_leagues(league_ids: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"leagues": {}, "errors": [], "seasons": []}
    seasons_seen: set[str] = set()
    for lid in league_ids:
        try:
            league_data = SleeperScraper.scrape_league_data(lid)
            if not league_data.get("success"):
                out["errors"].append(
                    {"league_id": lid, "error": league_data.get("error")}
                )
                out["leagues"][lid] = {"status": "error"}
                continue
            season = league_data.get("league_info", {}).get("season")
            if season:
                seasons_seen.add(str(season))
            save_result = DatabaseManager.save_league_data(league_data)
            if save_result.get("status") == "success":
                invalidate_dashboard_league(lid)
            out["leagues"][lid] = save_result
        except Exception as e:
            logger.exception("League refresh failed for %s", lid)
            out["errors"].append({"league_id": lid, "error": str(e)})
            out["leagues"][lid] = {"status": "error", "error": str(e)}
    out["seasons"] = sorted(seasons_seen)
    return out


def persist_research(
    season: str, week: int = 1, league_type: str = "dynasty"
) -> Dict[str, Any]:
    """Fetch research from Sleeper API and replace DB rows for season/week/league_type."""
    research = SleeperScraper.scrape_research_data(season, week, league_type)
    if not research.get("success"):
        return {
            "status": "error",
            "season": season,
            "error": research.get("error", "unknown"),
        }
    raw = research.get("research_data")
    if not isinstance(raw, dict):
        return {
            "status": "error",
            "season": season,
            "error": f"Unexpected research_data type: {type(raw).__name__}",
        }

    SleeperWeeklyData.query.filter_by(
        season=season, week=week, league_type=league_type
    ).delete()

    saved = 0
    for player_id, player_data in raw.items():
        try:
            rec = SleeperWeeklyData(
                season=season,
                week=week,
                league_type=league_type,
                player_id=str(player_id),
                research_data=json.dumps(player_data),
            )
            db.session.add(rec)
            saved += 1
        except Exception as e:
            logger.error("Research save failed for %s: %s", player_id, e)

    db.session.commit()
    return {
        "status": "success",
        "season": season,
        "week": week,
        "league_type": league_type,
        "saved_count": saved,
    }


def _bump_last_week_updated(league_id: str, week: int) -> None:
    """Advance SleeperLeagueStats.last_week_updated to ``week`` if higher than stored."""
    row = SleeperLeagueStats.query.filter_by(league_id=league_id).first()
    if not row:
        return
    if (row.last_week_updated or 0) < week:
        row.last_week_updated = week
        db.session.commit()


def refresh_weekly_stats_for_league(
    league_id: str,
    season: str,
    *,
    weeks: Iterable[int] = REGULAR_SEASON_WEEKS,
    league_type: str = "dynasty",
) -> Dict[str, Any]:
    """Fetch weekly matchup stats from Sleeper for a single league across one or more weeks.

    After each successful save, advances ``SleeperLeagueStats.last_week_updated``
    so callers can resume incrementally.
    """
    summary: Dict[str, Any] = {
        "league_id": league_id,
        "season": season,
        "league_type": league_type,
        "weeks": [],
        "errors": [],
    }
    for week in weeks:
        try:
            matchups = SleeperScraper.fetch_weekly_matchups(league_id, week)
            if not matchups:
                summary["weeks"].append({"week": week, "status": "no_data"})
                continue
            records = SleeperScraper.parse_weekly_matchups(matchups)
            if not records:
                summary["weeks"].append({"week": week, "status": "no_records"})
                continue
            save_result = DatabaseManager.save_weekly_stats(
                records, season, week, league_type
            )
            summary["weeks"].append({"week": week, **save_result})
            _bump_last_week_updated(league_id, week)
        except Exception as exc:
            logger.exception(
                "weekly stats fetch failed league=%s week=%s", league_id, week
            )
            summary["errors"].append({"week": week, "error": str(exc)})
    return summary


def refresh_weekly_stats_for_leagues(
    league_ids: List[str],
    *,
    weeks: Iterable[int] = REGULAR_SEASON_WEEKS,
) -> Dict[str, Any]:
    """Fetch weekly stats for many leagues. Uses each league's stored season."""
    league_seasons = _league_id_to_season()
    out: Dict[str, Any] = {"leagues": [], "errors": []}
    for lid in league_ids:
        season = league_seasons.get(lid)
        if not season:
            out["errors"].append({"league_id": lid, "error": "no season in DB"})
            continue
        try:
            out["leagues"].append(
                refresh_weekly_stats_for_league(lid, season, weeks=weeks)
            )
        except Exception as exc:
            logger.exception("weekly stats refresh failed for league %s", lid)
            out["errors"].append({"league_id": lid, "error": str(exc)})
    return out


def run_daily_refresh(
    *,
    league_ids: Optional[List[str]] = None,
    seasons: Optional[List[str]] = None,
    research_week: Optional[int] = None,
    skip_ktc: bool = False,
    skip_leagues: bool = False,
    skip_research: bool = False,
    skip_weekly_stats: bool = False,
) -> DailyRefreshSummary:
    """
    Run the full pipeline used for once-per-day updates.

    Order: KTC all formats -> configured leagues -> research per season.

    NFL player ingest (POST /api/sleeper/refresh) is intentionally excluded;
    it calls the slow Sleeper /v1/players/nfl endpoint and should only be
    triggered manually on rare occasions.

    When ``seasons`` is omitted, research seasons are derived from
    ``refresh_leagues`` results (each league's API response contains a
    ``season`` field). If ``skip_leagues`` is true and ``seasons`` is not
    provided, research is skipped and a warning is logged.
    """
    lids = league_ids if league_ids is not None else _league_ids_for_refresh()
    week = research_week if research_week is not None else int(
        os.getenv("DAILY_REFRESH_RESEARCH_WEEK", "1")
    )

    summary: DailyRefreshSummary = {
        "ktc": None,
        "leagues": None,
        "research": [],
        "weekly_stats": None,
        "errors": [],
    }

    if not skip_ktc:
        if not DatabaseManager.verify_database_connection():
            summary["ktc"] = {"overall_status": "error", "error": "Database connection failed"}
            summary["errors"].append({"step": "ktc", "error": "Database connection failed"})
        else:
            summary["ktc"] = scrape_and_save_all_ktc_data(KTCScraper, DatabaseManager)
            if summary["ktc"].get("overall_status") == "error":
                summary["errors"].append(
                    {"step": "ktc", "error": summary["ktc"].get("error", "KTC refresh failed")}
                )

    league_seasons: List[str] = []
    if not skip_leagues and lids:
        summary["leagues"] = refresh_leagues(lids)
        league_seasons = summary["leagues"].get("seasons", [])
        summary["errors"].extend(
            {**e, "step": "league"} for e in summary["leagues"].get("errors", [])
        )

    if not skip_research:
        seas = seasons if seasons is not None else league_seasons
        if not seas:
            logger.warning(
                "No seasons available for research refresh; pass seasons explicitly "
                "or ensure skip_leagues is false so seasons are derived from league data"
            )
        for s in seas:
            for lt in ("dynasty", "redraft"):
                try:
                    summary["research"].append(
                        persist_research(s, week=week, league_type=lt)
                    )
                except Exception as e:
                    logger.exception(
                        "Research refresh failed for season %s league_type=%s", s, lt
                    )
                    summary["research"].append(
                        {
                            "status": "error",
                            "season": s,
                            "league_type": lt,
                            "error": str(e),
                        }
                    )
                    summary["errors"].append(
                        {
                            "step": "research",
                            "season": s,
                            "league_type": lt,
                            "error": str(e),
                        }
                    )

    if not skip_weekly_stats and lids:
        try:
            summary["weekly_stats"] = refresh_weekly_stats_for_leagues(lids)
            for err in summary["weekly_stats"].get("errors", []):
                summary["errors"].append({"step": "weekly_stats", **err})
        except Exception as e:
            logger.exception("Weekly stats refresh failed")
            summary["errors"].append({"step": "weekly_stats", "error": str(e)})

    return summary
