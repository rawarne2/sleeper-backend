"""
Async KTC single-format refresh: job registry + background worker.

Default HTTP handler returns 202 quickly; heavy scrape/DB work runs in a daemon thread
with a Flask app context (suitable for Gunicorn/Docker). Serverless runtimes may freeze
the process after the response — see refresh route logs when VERCEL is set.
"""
from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional, Tuple

from managers.database_manager import DatabaseManager
from managers.file_manager import FileManager
from routes.helpers import filter_players_by_format
from routes.ktc.rankings_cache import invalidate_rankings_cache
from scrapers.ktc_scraper import KTCScraper
from scrapers.pipelines import load_sleeper_players_for_merge_from_db, scrape_and_process_data
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import (
    perform_file_operations,
    save_and_verify_database,
    setup_logging,
)

logger = setup_logging()

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}
_active_key_to_job: Dict[str, str] = {}

_MAX_JOBS = 400
_PRUNE_AFTER = timedelta(hours=2)


def _config_key(league_format: str, is_redraft: bool, tep_level: Optional[str]) -> str:
    tep = tep_level or ""
    return f"{league_format}:{int(is_redraft)}:{tep}"


def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except ValueError:
        return None


def _prune_finished_jobs_unlocked() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    now = datetime.now(UTC)
    terminal: List[Tuple[datetime, str]] = []
    for jid, rec in _jobs.items():
        if rec.get("status") not in ("succeeded", "failed"):
            continue
        fin = _parse_iso(rec.get("finished_at")) or _parse_iso(
            rec.get("created_at"))
        if fin is None:
            continue
        if fin.tzinfo is None:
            fin = fin.replace(tzinfo=UTC)
        if now - fin > _PRUNE_AFTER:
            terminal.append((fin, jid))
    terminal.sort(key=lambda x: x[0])
    for _, jid in terminal[: max(0, len(_jobs) - _MAX_JOBS + 50)]:
        _jobs.pop(jid, None)


@dataclass
class KTCRefreshOutcome:
    ok: bool
    status_code: int
    body: Dict[str, Any]


def execute_ktc_refresh_pipeline(
    league_format: str,
    is_redraft: bool,
    tep_level: Optional[str],
) -> KTCRefreshOutcome:
    """
    Full synchronous pipeline: scrape KTC, save DB, optional file/S3, invalidate cache.
    Used by sync refresh and by the background worker.
    """
    if not DatabaseManager.verify_database_connection():
        logger.error("Database connection verification failed before refresh")
        return KTCRefreshOutcome(
            False,
            500,
            {
                "error": "Database connection failed",
                "details": "Cannot establish database connection before starting refresh operation",
                "database_success": False,
            },
        )

    try:
        sleeper_for_merge = load_sleeper_players_for_merge_from_db()
    except Exception as e:
        logger.warning(
            "Could not preload Sleeper rows for merge, pipeline will load or skip: %s", e
        )
        sleeper_for_merge = None

    players_sorted, scrape_error = scrape_and_process_data(
        KTCScraper,
        league_format,
        is_redraft,
        tep_level,
        sleeper_for_merge,
    )
    if scrape_error:
        return KTCRefreshOutcome(
            False,
            500,
            {
                "error": "No players found during scraping",
                "details": scrape_error,
                "database_success": False,
            },
        )

    added_count, db_error = save_and_verify_database(
        DatabaseManager, players_sorted, league_format, is_redraft
    )
    if db_error:
        return KTCRefreshOutcome(
            False,
            500,
            {
                "error": "Database operation failed",
                "details": db_error,
                "scraped_count": len(players_sorted),
                "database_success": False,
            },
        )

    file_saved, s3_uploaded = perform_file_operations(
        FileManager, players_sorted, added_count, league_format, is_redraft, tep_level
    )
    filtered_players = filter_players_by_format(
        players_sorted, league_format, tep_level
    )
    invalidate_rankings_cache(
        is_redraft=is_redraft, league_format=league_format, tep_level=tep_level
    )

    return KTCRefreshOutcome(
        True,
        200,
        {
            "message": "Rankings updated successfully",
            "timestamp": utc_now_rfc3339(),
            "database_success": True,
            "file_saved": file_saved,
            "s3_uploaded": s3_uploaded,
            "is_redraft": is_redraft,
            "league_format": league_format,
            "tep_level": tep_level,
            "count": len(filtered_players),
            "players": filtered_players,
            "operations_summary": {
                "players_count": len(filtered_players),
                "database_saved_count": added_count,
                "file_saved": file_saved,
                "s3_uploaded": s3_uploaded,
            },
        },
    )


def get_refresh_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        rec = _jobs.get(job_id)
        if rec is None:
            return None
        return dict(rec)


def _release_active_slot(cfg_key: str, job_id: str) -> None:
    with _lock:
        if _active_key_to_job.get(cfg_key) == job_id:
            del _active_key_to_job[cfg_key]


def _worker(
    app: Any,
    job_id: str,
    cfg_key: str,
    league_format: str,
    is_redraft: bool,
    tep_level: Optional[str],
) -> None:
    try:
        with app.app_context():
            with _lock:
                j = _jobs.get(job_id)
                if j:
                    j["status"] = "running"
            outcome = execute_ktc_refresh_pipeline(
                league_format, is_redraft, tep_level
            )
            with _lock:
                j = _jobs.get(job_id)
                if j:
                    j["status"] = "succeeded" if outcome.ok else "failed"
                    j["finished_at"] = utc_now_rfc3339()
                    j["http_status"] = outcome.status_code
                    if outcome.ok:
                        j["error"] = None
                        osum = outcome.body.get("operations_summary") or {}
                        j["summary"] = {
                            "players_count": osum.get("players_count"),
                            "database_saved_count": osum.get("database_saved_count"),
                            "file_saved": osum.get("file_saved"),
                            "s3_uploaded": osum.get("s3_uploaded"),
                        }
                    else:
                        j["error"] = outcome.body.get("error") or outcome.body.get(
                            "details"
                        )
                        j["summary"] = None
            if not outcome.ok:
                logger.error(
                    "KTC async refresh job %s failed: %s",
                    job_id,
                    outcome.body.get("error") or outcome.body.get("details"),
                )
    except Exception as e:
        logger.exception("KTC async refresh job %s crashed: %s", job_id, e)
        with _lock:
            j = _jobs.get(job_id)
            if j:
                j["status"] = "failed"
                j["finished_at"] = utc_now_rfc3339()
                j["error"] = str(e)
                j["summary"] = None
    finally:
        _release_active_slot(cfg_key, job_id)


def try_begin_async_job(
    app: Any,
    league_format: str,
    is_redraft: bool,
    tep_level: Optional[str],
) -> Tuple[str, bool]:
    """
    Start a background refresh unless one is already queued/running for this config.

    Returns:
        (job_id, already_running)
    """
    cfg_key = _config_key(league_format, is_redraft, tep_level)
    if os.getenv("VERCEL"):
        logger.warning(
            "KTC refresh running in a background thread on Vercel/serverless; "
            "work may not finish after the HTTP response. Use sync=1 for a blocking "
            "refresh in the same invocation, or rely on POST /api/ktc/refresh/all / nightly sync."
        )

    with _lock:
        _prune_finished_jobs_unlocked()
        existing_id = _active_key_to_job.get(cfg_key)
        if existing_id:
            job = _jobs.get(existing_id)
            if job and job.get("status") in ("queued", "running"):
                return existing_id, True

        job_id = str(uuid.uuid4())
        now = utc_now_rfc3339()
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "finished_at": None,
            "league_format": league_format,
            "is_redraft": is_redraft,
            "tep_level": tep_level or "",
            "error": None,
            "http_status": None,
            "summary": None,
        }
        _active_key_to_job[cfg_key] = job_id

    thread = threading.Thread(
        target=_worker,
        args=(app, job_id, cfg_key, league_format, is_redraft, tep_level),
        daemon=True,
        name=f"ktc-refresh-{job_id[:8]}",
    )
    thread.start()
    return job_id, False
