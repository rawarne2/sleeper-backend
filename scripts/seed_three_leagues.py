#!/usr/bin/env python
"""
Seed the local DB with everything needed for the three example dynasty
superflex leagues so the dashboard endpoint never has to scrape on a request.
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

THREE_LEAGUES = [
    "1050831680350568448",  # 2024 dynasty superflex
    "1210364682523656192",  # 2025 dynasty superflex
    "1333945997071515648",  # 2026 dynasty superflex
]

_EPILOG = textwrap.dedent(
    """
    What each mode does
    -------------------
    Idempotent (default)    Ensures schema exists, re-runs the same daily refresh
                            pipeline. Safe to run repeatedly. Updates/replaces
                            KTC, league, and stats data; it does not wipe the DB.

    --reset (destructive)  Drops every table, then re-seeds. Use only when you
                            want a clean database.

    NFL player ingest
    ----------------
    If the players table is empty, the script fetches NFL players from Sleeper
    (unless you pass --skip-nfl). This is a normal one-time (or re-)ingest, not
    a full DB drop.

    --skip-nfl (non-destructive)  Never call Sleeper NFL player ingest, even
                            when the table is empty. Use when you already have
                            player rows or are testing the pipeline in isolation.
                            Idempotent: it only *skips* that step; it does not
                            delete player rows.

    --force-nfl              Always run NFL ingest, even if rows already exist.
                            Can refresh Sleeper player metadata at the cost of time.

    Related scripts
    ---------------
    ``scripts/run_all_requests_three_leagues.sh`` is different: it curl's a
    *running* API (nightly-sync, daily-refresh, per-league routes) for HTTP smoke
    / integration. It does not run this in-process seed.
    """
).strip()


def _print_summary(summary: dict) -> None:
    ktc = summary.get("ktc") or {}
    leagues = (summary.get("leagues") or {}).get("leagues") or {}
    research = summary.get("research") or []
    weekly = (summary.get("weekly_stats") or {}).get("leagues") or []
    errors = summary.get("errors") or []

    league_ok = sum(1 for v in leagues.values() if v.get("status") == "success")
    research_ok = sum(1 for r in research if r.get("status") == "success")

    print("Summary:")
    print(f"  KTC overall: {ktc.get('overall_status', 'n/a')}")
    print(f"  Leagues refreshed: {league_ok}/{len(leagues)}")
    print(f"  Research entries: {research_ok}/{len(research)} succeeded")
    print(f"  Weekly stats leagues processed: {len(weekly)}")
    print(f"  Errors: {len(errors)}")
    for e in errors[:10]:
        print(f"    - {e}")
    if len(errors) > 10:
        print(f"    ... and {len(errors) - 10} more")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.strip().split("\n", 1)[0],
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate every table before seeding (destructive; otherwise idempotent re-run).",
    )
    parser.add_argument(
        "--skip-nfl",
        action="store_true",
        help="Do not run Sleeper NFL player ingest, even if the players table is empty (non-destructive; see epilog).",
    )
    parser.add_argument(
        "--force-nfl",
        action="store_true",
        help="Always run Sleeper NFL player ingest, even if rows already exist.",
    )
    args = parser.parse_args()

    if args.skip_nfl and args.force_nfl:
        print("Use either --skip-nfl or --force-nfl, not both", file=sys.stderr)
        return 2

    from app import app, db  # noqa: E402
    from managers.database_manager import DatabaseManager  # noqa: E402
    from models.entities import Player  # noqa: E402
    from scrapers.sleeper_scraper import SleeperScraper  # noqa: E402
    from services.daily_refresh import run_daily_refresh  # noqa: E402

    with app.app_context():
        if args.reset:
            print("--reset: dropping and recreating every table")
            db.drop_all()
            db.create_all()
        else:
            db.create_all()

        existing_players = Player.query.count()
        print(f"Existing players in DB: {existing_players}")

        if args.skip_nfl:
            print("--skip-nfl: leaving NFL player rows untouched")
        elif args.force_nfl or existing_players == 0:
            print("Ingesting Sleeper NFL player data (this can take 30-60s)...")
            t = time.perf_counter()
            sleeper_players = SleeperScraper.scrape_sleeper_data()
            if not sleeper_players:
                print(
                    "SleeperScraper.scrape_sleeper_data() returned empty; aborting",
                    file=sys.stderr,
                )
                return 1
            result = DatabaseManager.save_sleeper_data_to_db(sleeper_players)
            if result.get("status") != "success":
                print(
                    f"NFL player save failed: {result.get('error')}",
                    file=sys.stderr,
                )
                return 1
            print(
                f"  saved/updated {result.get('total_processed', 0)} players, "
                f"pruned {result.get('pruned_stale_players', 0)} stale rows in "
                f"{(time.perf_counter() - t):.1f}s"
            )

        print("Running daily refresh pipeline for the 3 example leagues...")
        t = time.perf_counter()
        summary = run_daily_refresh(league_ids=THREE_LEAGUES)
        print(f"  pipeline completed in {(time.perf_counter() - t):.1f}s")
        _print_summary(summary)

    print("Seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
