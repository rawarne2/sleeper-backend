#!/usr/bin/env python3
"""
Apply the value_snapshots retention policy (services/valuations/retention.py):
  - ``value``: keep everything from the last 30 days, then one row per key per day.
  - every other metric: keep only the latest row per key.

Targets the app DB from .env (DATABASE_URL); drops TEST_DATABASE_URI when DATABASE_URL is set.

  Dry run (default): python scripts/prune_value_snapshots.py
  Apply deletes:     python scripts/prune_value_snapshots.py --execute

Deletes free space for reuse; run VACUUM FULL value_snapshots afterwards to return it
to the OS (and shrink the Supabase disk-size figure).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune value_snapshots per the retention policy.")
    parser.add_argument("--execute", action="store_true", help="Delete rows (default: dry run).")
    parser.add_argument("--keep-all-days", type=int, default=None,
                        help="Days of full-resolution history to keep (default: policy value).")
    parser.add_argument("--batch-size", type=int, default=5000)
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

    import app  # noqa: F401,E402 - importing configures the db engine
    from models.extensions import db, session_scope  # noqa: E402
    from services.valuations.retention import KEEP_ALL_DAYS, prune_value_snapshots  # noqa: E402

    with session_scope():
        print(f"Effective database: {db.engine.url.render_as_string(hide_password=True)}")
        started = time.perf_counter()
        report = prune_value_snapshots(
            dry_run=not args.execute,
            keep_all_days=args.keep_all_days if args.keep_all_days is not None else KEEP_ALL_DAYS,
            batch_size=args.batch_size,
        )
        for name, n in sorted(report.deleted.items()):
            print(f"  {name}: {n}")
        verb = "Would delete" if report.dry_run else "Deleted"
        print(f"{verb} {report.total} row(s) (full-history cutoff {report.cutoff:%Y-%m-%d %H:%M} UTC) "
              f"in {time.perf_counter() - started:.1f}s.")
        if report.dry_run and report.total:
            print("Dry run only. Re-run with --execute to delete these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
