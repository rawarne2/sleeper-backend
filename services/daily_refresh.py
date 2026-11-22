"""
Orchestration for daily / scheduled data refresh (KTC + leagues + research + weekly stats).

Kept separate from route handlers so it can be called from a route or a CLI.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from cache.redis_dashboard import invalidate_dashboard_league
from managers.database_manager import DatabaseManager
from models.entities import SleeperLeague, SleeperLeagueStats, SleeperWeeklyData
from models.extensions import db
from routes.sleeper.research import (
    _upsert_research_rows,
    research_weeks_to_persist,
)
from scrapers.ktc_scraper import KTCScraper
from scrapers.pipelines import scrape_and_save_all_ktc_data
from scrapers.sleeper_scraper import SleeperScraper
from services.news_ingest import ingest_player_news
from services.nflverse_ingest import ingest_nflverse_injuries
from services.types import DailyRefreshSummary
from utils.constants import EXAMPLE_LEAGUE_IDS
from utils.helpers import setup_logging

logger = setup_logging(__name__)

REGULAR_SEASON_WEEKS = range(1, 19)  # Sleeper uses weeks 1..18 for regular season + week 18


def _league_ids_for_refresh(session: Session | None = None) -> List[str]:
    """All league IDs persisted in the DB; fall back to built-in defaults if none.

    Only league_id is needed here — season is resolved via the Sleeper API at
    refresh time. Unlike _prewarm_dashboard_caches(), rows with NULL season are
    still valid refresh targets.
    """
    session = session or db.session
    rows = session.execute(select(SleeperLeague.league_id)).all()
    out = [r[0] for r in rows if r and r[0]]
    if out:
        return out
    return [lid for lid, _ in EXAMPLE_LEAGUE_IDS]


def _league_id_to_season(session: Session | None = None) -> Dict[str, str]:
    """Map league_id -> season for all leagues persisted in the DB."""
    session = session or db.session
    rows = session.execute(
        select(SleeperLeague.league_id, SleeperLeague.season)
    ).all()
    return {r[0]: str(r[1]) for r in rows if r and r[0] and r[1]}


def _current_research_season(candidates: Optional[Iterable[str]] = None) -> str:
    """Pick the active season for the retention policy: max(candidates) or calendar year."""
    valid: List[str] = []
    if candidates:
        for s in candidates:
            text = str(s).strip()
            if len(text) == 4 and text.isdigit():
                valid.append(text)
    if valid:
        return max(valid)
    return str(datetime.now(UTC).year)


def _current_season() -> str:
    """The season scheduled refreshes operate on — the current calendar year.

    Prior seasons are immutable (research, weekly stats, and final standings no
    longer change), so the nightly cron re-scrapes only this season.
    """
    return str(datetime.now(UTC).year)


def _current_season_league_ids(
    current_season: str, session: Session | None = None
) -> List[str]:
    """League IDs to refresh on the scheduled path: only current-season leagues.

    Falls back to the built-in example leagues for ``current_season`` when the DB
    has none, and finally to every persisted league (with a warning) so the cron
    never silently refreshes nothing.
    """
    session = session or db.session
    rows = session.execute(
        select(SleeperLeague.league_id)
        .where(SleeperLeague.season == current_season)
    ).all()
    out = [r[0] for r in rows if r and r[0]]
    if out:
        return out

    seeded = [lid for lid, season in EXAMPLE_LEAGUE_IDS if season == current_season]
    if seeded:
        return seeded

    logger.warning(
        "No leagues found for current season %s; refreshing all persisted leagues",
        current_season,
    )
    return _league_ids_for_refresh(session=session)


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
    """Upsert one week of research; matchup-derived columns are preserved."""
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

    counts = _upsert_research_rows(season, int(week), league_type, raw)
    return {
        "status": "success",
        "season": season,
        "week": week,
        "league_type": league_type,
        "saved_count": counts["saved_count"],
        "inserted": counts["inserted"],
        "updated": counts["updated"],
        "skipped": counts["skipped"],
    }


def _bump_last_week_updated(
    league_id: str, week: int, session: Session | None = None
) -> None:
    """Advance SleeperLeagueStats.last_week_updated to ``week`` if higher than stored."""
    session = session or db.session
    row = session.execute(
        select(SleeperLeagueStats).filter_by(league_id=league_id)
    ).scalars().first()
    if not row:
        return
    if (row.last_week_updated or 0) < week:
        row.last_week_updated = week
        session.commit()


def refresh_weekly_stats_for_league(
    league_id: str,
    season: str,
    *,
    weeks: Iterable[int] = REGULAR_SEASON_WEEKS,
    league_type: str = "dynasty",
    session: Session | None = None,
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
                records, season, week, league_type, session=session
            )
            summary["weeks"].append({"week": week, **save_result})
            _bump_last_week_updated(league_id, week, session=session)
        except Exception as exc:
            logger.exception(
                "weekly stats fetch failed league=%s week=%s", league_id, week
            )
            summary["errors"].append({"week": week, "error": str(exc)})
    return summary


def ingest_nfl_week_stats(season: str, *, weeks: Iterable[int] = REGULAR_SEASON_WEEKS) -> Dict[str, int]:
    """Ingest league-agnostic raw Sleeper stat lines for a season (weeks 1–18).

    One row per player/week in ``nfl_player_week_stats``; the scoring engine
    dot-products these against each league's ``scoring_settings`` to reproduce
    Sleeper points for the whole player universe.
    """
    totals = {"saved": 0, "updated": 0, "skipped": 0}
    for week in weeks:
        raw = SleeperScraper.fetch_weekly_player_stats(season, week)
        if not raw:
            continue
        res = DatabaseManager.save_nfl_week_stats(season, week, raw)
        for k in totals:
            totals[k] += res.get(k, 0)
    return totals


def _stats_weeks(season: str, nfl_state: dict | None) -> range:
    """None requests a full backfill. A live state bounds the scheduled refresh."""
    if nfl_state is None:
        return REGULAR_SEASON_WEEKS
    active = nfl_state.get("season")
    if not active:
        raise ValueError("Sleeper NFL season unavailable for scheduled stats")
    if int(season) < int(active):
        return REGULAR_SEASON_WEEKS
    if int(season) > int(active) or nfl_state.get("season_type") in ("pre", "off"):
        return range(0)
    if nfl_state.get("season_type") == "post":
        return REGULAR_SEASON_WEEKS
    if nfl_state.get("season_type") != "regular" or nfl_state.get("week") is None:
        raise ValueError("Sleeper NFL week unavailable for scheduled stats")
    return range(1, min(int(nfl_state["week"]), REGULAR_SEASON_WEEKS[-1]) + 1)


def refresh_weekly_stats_for_leagues(
    league_ids: List[str],
    *,
    weeks: Iterable[int] | None = None,
    nfl_state: dict | None = None,
    session: Session | None = None,
) -> Dict[str, Any]:
    """Fetch weekly stats for many leagues. Uses each league's stored season."""
    session = session or db.session
    league_seasons = _league_id_to_season(session=session)
    out: Dict[str, Any] = {"leagues": [], "errors": []}
    for lid in league_ids:
        season = league_seasons.get(lid)
        if not season:
            out["errors"].append({"league_id": lid, "error": "no season in DB"})
            continue
        try:
            out["leagues"].append(
                refresh_weekly_stats_for_league(
                    lid, season, weeks=weeks if weeks is not None else _stats_weeks(season, nfl_state),
                    session=session,
                )
            )
        except Exception as exc:
            logger.exception("weekly stats refresh failed for league %s", lid)
            out["errors"].append({"league_id": lid, "error": str(exc)})
    return out


def _default_research_week() -> int:
    """``DAILY_REFRESH_RESEARCH_WEEK`` override, else Sleeper's current regular-season week."""
    override = os.getenv("DAILY_REFRESH_RESEARCH_WEEK")
    if override:
        return int(override)
    state = SleeperScraper.fetch_nfl_state() or {}
    if state.get("season_type") == "regular" and state.get("week"):
        return min(int(state["week"]), REGULAR_SEASON_WEEKS[-1])
    if state.get("season_type") == "post":
        return REGULAR_SEASON_WEEKS[-1]
    return 1


def run_daily_refresh(
    *,
    league_ids: Optional[List[str]] = None,
    seasons: Optional[List[str]] = None,
    research_week: Optional[int] = None,
    skip_ktc: bool = False,
    skip_leagues: bool = False,
    skip_research: bool = False,
    skip_weekly_stats: bool = False,
    skip_nfl_stats: bool = False,
    backfill_stats: bool = False,
    skip_injuries: bool = False,
    skip_news: bool = False,
    session: Session | None = None,
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
    provided, the scheduled path researches the current season; with explicit
    ``league_ids`` research is skipped and a warning is logged.

    Each ``skip_*`` flag isolates one step so callers (the chunked GitHub Actions
    nightly) can run the pipeline as several short requests.

    The scheduled (no-argument) path is **scoped to the current season**: prior
    seasons are immutable, so re-scraping them nightly is wasted work. Pass
    explicit ``league_ids`` / ``seasons`` to back-fill older data on demand.
    """
    session = session or db.session
    nfl_state = None
    if not backfill_stats and not (skip_weekly_stats and skip_nfl_stats):
        nfl_state = SleeperScraper.fetch_nfl_state() or {}
    current_season = str((nfl_state or {}).get("season") or _current_season())
    lids = (
        league_ids
        if league_ids is not None
        else _current_season_league_ids(current_season, session=session)
    )
    week = research_week if research_week is not None else (
        1 if skip_research else _default_research_week()
    )

    summary: DailyRefreshSummary = {
        "ktc": None,
        "leagues": None,
        "research": [],
        "weekly_stats": None,
        "nfl_week_stats": None,
        "errors": [],
    }

    if not skip_ktc:
        if not DatabaseManager.verify_database_connection():
            summary["ktc"] = {"overall_status": "error", "error": "Database connection failed"}
            summary["errors"].append({"step": "ktc", "error": "Database connection failed"})
        else:
            summary["ktc"] = scrape_and_save_all_ktc_data(KTCScraper, DatabaseManager, session=session)
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
        if not seas and skip_leagues and league_ids is None:
            seas = [current_season]
        if not seas:
            logger.warning(
                "No seasons available for research refresh; pass seasons explicitly "
                "or ensure skip_leagues is false so seasons are derived from league data"
            )
        current_season = _current_research_season(seas)
        for s in seas:
            weeks_for_season, truncated = research_weeks_to_persist(
                s,
                week_param=week,
                fetch_all_weeks=False,
                current_season=current_season,
            )
            if truncated:
                logger.info(
                    "Daily research retention applied season=%s requested_week=%s -> weeks=%s",
                    s,
                    week,
                    weeks_for_season,
                )
            for wk in weeks_for_season:
                for lt in ("dynasty", "redraft"):
                    try:
                        summary["research"].append(
                            persist_research(s, week=wk, league_type=lt)
                        )
                    except Exception as e:
                        logger.exception(
                            "Research refresh failed for season %s week %s league_type=%s",
                            s,
                            wk,
                            lt,
                        )
                        summary["research"].append(
                            {
                                "status": "error",
                                "season": s,
                                "week": wk,
                                "league_type": lt,
                                "error": str(e),
                            }
                        )
                        summary["errors"].append(
                            {
                                "step": "research",
                                "season": s,
                                "week": wk,
                                "league_type": lt,
                                "error": str(e),
                            }
                        )

    if not skip_weekly_stats and lids:
        try:
            summary["weekly_stats"] = refresh_weekly_stats_for_leagues(lids, nfl_state=nfl_state, session=session)
            for err in summary["weekly_stats"].get("errors", []):
                summary["errors"].append({"step": "weekly_stats", **err})
        except Exception as e:
            logger.exception("Weekly stats refresh failed")
            summary["errors"].append({"step": "weekly_stats", "error": str(e)})

    if not skip_nfl_stats:
        # Ingest league-agnostic raw NFL stat lines once per distinct season so the
        # scoring engine can compute league-accurate points for the whole universe.
        # On the scheduled path (no explicit seasons) this is the current season
        # only; prior-season stat lines are final and never change.
        ingest_seasons = {
            s for s in (seasons or league_seasons or [current_season])
            if s and str(s).strip()
        }
        if ingest_seasons:
            nfl_stats: Dict[str, Any] = {}
            for s in sorted(ingest_seasons):
                try:
                    nfl_stats[s] = ingest_nfl_week_stats(str(s), weeks=_stats_weeks(str(s), nfl_state))
                except Exception as e:
                    logger.exception("NFL week stats ingest failed for season %s", s)
                    summary["errors"].append(
                        {"step": "nfl_week_stats", "season": s, "error": str(e)}
                    )
            summary["nfl_week_stats"] = nfl_stats

    # Official injury reports (nflverse, CC-BY, no key) + per-player news (Tank01,
    # needs RAPIDAPI_KEY). Each is isolated so a failure never aborts the cron.
    injury_seasons = {
        s for s in (seasons or league_seasons or [_current_season()]) if s and str(s).strip()
    }
    if injury_seasons and not skip_injuries:
        injuries: Dict[str, Any] = {}
        for s in sorted(injury_seasons):
            try:
                injuries[str(s)] = ingest_nflverse_injuries(str(s), session=session)
            except Exception as e:
                logger.exception("nflverse injuries ingest failed for season %s", s)
                summary["errors"].append({"step": "injuries", "season": s, "error": str(e)})
        summary["injuries"] = injuries

    if not skip_news:
        try:
            summary["news"] = ingest_player_news(session=session)
        except Exception as e:
            logger.exception("Player news ingest failed")
            summary["errors"].append({"step": "news", "error": str(e)})

    return summary
