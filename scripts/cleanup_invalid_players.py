#!/usr/bin/env python3
"""
Delete players rows that should never be persisted:
  - missing/empty match_key, or
  - search_rank == SLEEPER_SEARCH_RANK_EXCLUDE (Sleeper placeholder / non-rosterable).

Uses the Flask app DB URI from the environment (e.g. Supabase DATABASE_URL).

If both TEST_DATABASE_URI and DATABASE_URL are set (common for local pytest),
loads .env then drops TEST_DATABASE_URI when DATABASE_URL is present so cleanup
targets the same DB as production, not SQLite / test Postgres.

  Dry run (default): python scripts/cleanup_invalid_players.py
  Apply deletes:     python scripts/cleanup_invalid_players.py --execute

Deletes use the ORM (not bulk DELETE) so child rows (KTC value tables) cascade.
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_BATCH = 500


def _mask_database_url(url: str | None) -> str:
    if not url:
        return "(none)"
    p = urlparse(url)
    host = p.hostname or "?"
    port = f":{p.port}" if p.port else ""
    db = (p.path or "").lstrip("/") or "?"
    return f"{p.scheme}://{host}{port}/{db}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove invalid player rows from Postgres.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows (default is count-only dry run).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-criterion row counts (overlapping; sum can exceed total matches).",
    )
    args = parser.parse_args()

    os.chdir(_ROOT)
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(os.path.join(_ROOT, ".env"))
        if os.getenv("DATABASE_URL"):
            os.environ.pop("TEST_DATABASE_URI", None)

    from app import app  # noqa: E402
    from models.entities import Player  # noqa: E402
    from models.extensions import db  # noqa: E402
    from sqlalchemy import or_  # noqa: E402
    from utils.constants import SLEEPER_SEARCH_RANK_EXCLUDE  # noqa: E402

    invalid = or_(
        Player.match_key.is_(None),
        Player.match_key == "",
        Player.search_rank == SLEEPER_SEARCH_RANK_EXCLUDE,
    )

    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        print(f"Effective database: {_mask_database_url(uri)}")

        if args.verbose:
            ex = SLEEPER_SEARCH_RANK_EXCLUDE
            print(
                "  breakdown (overlapping): "
                f"match_key NULL={Player.query.filter(Player.match_key.is_(None)).count()}, "
                f"match_key ''={Player.query.filter(Player.match_key == '').count()}, "
                f"search_rank=={ex}={Player.query.filter(Player.search_rank == ex).count()}"
            )

        n = Player.query.filter(invalid).count()
        print(f"Rows matching cleanup criteria: {n}")
        if n == 0:
            return 0
        if not args.execute:
            print("Dry run only. Re-run with --execute to delete these rows.")
            return 0

        deleted = 0
        while True:
            batch = Player.query.filter(invalid).limit(_BATCH).all()
            if not batch:
                break
            for row in batch:
                db.session.delete(row)
            deleted += len(batch)
            db.session.commit()
            print(f"  committed {deleted}...")
        print(f"Deleted {deleted} player row(s). Re-run KTC + Sleeper refresh to repopulate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
