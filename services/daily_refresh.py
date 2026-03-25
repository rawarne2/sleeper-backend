"""
Orchestration for daily / scheduled data refresh (Sleeper + KTC + leagues + research).

Kept separate from route handlers so it can be called from Flask or a CLI later.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from managers import DatabaseManager
from models import SleeperWeeklyData, db
from scrapers import KTCScraper, SleeperScraper, scrape_and_save_all_ktc_data
from utils import setup_logging

logger = setup_logging()


def _default_league_ids() -> List[str]:
    raw = (os.getenv("DAILY_REFRESH_LEAGUE_IDS") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [
        "1333945997071515648",
        "1210364682523656192",
        "1050831680350568448",
    ]


def _resolve_league_ids() -> List[str]:
    flag = (os.getenv("NIGHTLY_SYNC_ALL_DB_LEAGUES") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        from models import SleeperLeague

        rows = SleeperLeague.query.with_entities(SleeperLeague.league_id).all()
        out = [r[0] for r in rows if r and r[0]]
        if out:
            return out
    return _default_league_ids()


def _default_seasons() -> List[str]:
    raw = (os.getenv("DAILY_REFRESH_SEASONS") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["2024", "2025", "2026"]


def refresh_sleeper_master_players() -> Dict[str, Any]:
    """Fetch NFL players from Sleeper and merge into DB (same as POST /api/sleeper/refresh)."""
    if not DatabaseManager.verify_database_connection():
        return {"status": "error", "error": "Database connection failed"}
    sleeper_players = SleeperScraper.scrape_sleeper_data()
    if not sleeper_players:
        return {
            "status": "error",
            "error": "No Sleeper players returned",
        }
    merge_result = DatabaseManager.save_sleeper_data_to_db(sleeper_players)
    if merge_result.get("status") == "error":
        return {
            "status": "error",
            "error": merge_result.get("error", "merge failed"),
        }
    return {"status": "success", "count": len(sleeper_players), "merge": merge_result}


def refresh_leagues(league_ids: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"leagues": {}, "errors": []}
    for lid in league_ids:
        try:
            league_data = SleeperScraper.scrape_league_data(lid)
            if not league_data.get("success"):
                out["errors"].append(
                    {"league_id": lid, "error": league_data.get("error")}
                )
                out["leagues"][lid] = {"status": "error"}
                continue
            save_result = DatabaseManager.save_league_data(league_data)
            out["leagues"][lid] = save_result
        except Exception as e:
            logger.exception("League refresh failed for %s", lid)
            out["errors"].append({"league_id": lid, "error": str(e)})
            out["leagues"][lid] = {"status": "error", "error": str(e)}
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


def run_daily_refresh(
    *,
    league_ids: Optional[List[str]] = None,
    seasons: Optional[List[str]] = None,
    research_week: Optional[int] = None,
    skip_sleeper_players: bool = False,
    skip_ktc: bool = False,
    skip_leagues: bool = False,
    skip_research: bool = False,
) -> Dict[str, Any]:
    """
    Run the full pipeline used for once-per-day updates.

    Order: Sleeper NFL players → KTC all formats → configured leagues → research per season.
    """
    lids = league_ids if league_ids is not None else _resolve_league_ids()
    seas = seasons if seasons is not None else _default_seasons()
    week = research_week if research_week is not None else int(
        os.getenv("DAILY_REFRESH_RESEARCH_WEEK", "1")
    )

    summary: Dict[str, Any] = {
        "sleeper_players": None,
        "ktc": None,
        "leagues": None,
        "research": [],
        "errors": [],
    }

    if not skip_sleeper_players:
        summary["sleeper_players"] = refresh_sleeper_master_players()
        if summary["sleeper_players"].get("status") == "error":
            summary["errors"].append(
                {"step": "sleeper_players", "error": summary["sleeper_players"].get("error")}
            )

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

    if not skip_leagues and lids:
        summary["leagues"] = refresh_leagues(lids)
        summary["errors"].extend(
            {**e, "step": "league"} for e in summary["leagues"].get("errors", [])
        )

    if not skip_research:
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

    return summary
