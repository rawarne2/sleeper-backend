"""Probe ``api.sleeper.app/players/nfl/research/regular`` for the union of keys.

The dashboard and trade analyzer currently only consume ``owned`` and ``started``
from the research payload (the analyzer exposes them as ``market_owned_pct`` /
``market_started_pct`` with week on ``league.research_week``), but ``SleeperWeeklyData`` carries placeholder columns
(``projected_points``, ``snap_count``, ``weather_condition``, …) that were never
hooked up. This script samples a grid of seasons × weeks × league_type and
prints the union of keys actually returned per player blob so the team can
decide which (if any) deserve UI / LLM columns instead of guessing.

Usage::

    python sleeper-backend/scripts/probe_sleeper_research_keys.py \
        --seasons 2024 2025 \
        --weeks 1 9 18 \
        --output sleeper-backend/docs/sleeper-research-payload-keys.md

If ``--output`` is omitted the report is printed to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Iterable, List

import requests


SLEEPER_BASE_URL = "https://api.sleeper.app/players/nfl/research/regular"
DEFAULT_SEASONS = ("2024", "2025")
DEFAULT_WEEKS = (1, 9, 18)
DEFAULT_LEAGUE_TYPES = ("dynasty", "redraft")
LEAGUE_TYPE_TO_INT = {"dynasty": 2, "redraft": 1}


def _fetch(season: str, week: int, league_type: str, timeout: float) -> dict | None:
    lt_int = LEAGUE_TYPE_TO_INT[league_type]
    url = f"{SLEEPER_BASE_URL}/{season}/{week}?league_type={lt_int}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        print(f"warn: {url} -> {exc}", file=sys.stderr)
        return None
    if not isinstance(body, dict):
        print(f"warn: {url} -> unexpected payload {type(body).__name__}",
              file=sys.stderr)
        return None
    return body


def _scan(payload: dict, key_counts: Counter, samples: Dict[str, list]) -> int:
    """Count keys + capture up to a few example values per key."""
    if not payload:
        return 0
    for player_id, blob in payload.items():
        if not isinstance(blob, dict):
            continue
        for key, value in blob.items():
            key_counts[key] += 1
            if len(samples[key]) < 3:
                samples[key].append({"player_id": str(player_id), "value": value})
    return len(payload)


def _render_markdown(
    grid: List[dict],
    key_counts: Counter,
    samples: Dict[str, list],
    total_players: int,
) -> str:
    lines: List[str] = []
    now = datetime.now(UTC).isoformat()
    lines.append("# Sleeper research payload keys (probe report)\n")
    lines.append(f"_Generated {now}._\n")
    lines.append("Endpoint sample: `GET /players/nfl/research/regular/{season}/{week}?league_type={1|2}`\n")
    lines.append("## Grid sampled\n")
    lines.append("| season | week | league_type | players observed |")
    lines.append("|---|---|---|---|")
    for entry in grid:
        lines.append(
            f"| {entry['season']} | {entry['week']} | {entry['league_type']} | {entry['count']} |"
        )
    lines.append("")
    lines.append(f"Total player blobs inspected: **{total_players}**\n")
    lines.append("## Key coverage (union across all samples)\n")
    if not key_counts:
        lines.append("_No keys observed._\n")
    else:
        lines.append("| key | occurrences | coverage % | example values |")
        lines.append("|---|---|---|---|")
        for key, count in key_counts.most_common():
            coverage = (count / total_players * 100) if total_players else 0.0
            example = ", ".join(
                f"`{json.dumps(s['value'])[:40]}` (pid {s['player_id']})"
                for s in samples[key][:3]
            )
            lines.append(f"| `{key}` | {count} | {coverage:.1f}% | {example} |")
        lines.append("")
        lines.append("## Suggested action\n")
        lines.append(
            "Keys that consistently appear (>50% coverage) are real product "
            "candidates; rare keys are likely transient (e.g. inactive players)."
        )
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons", nargs="+", default=list(DEFAULT_SEASONS),
        help="Seasons to probe (default: %(default)s)",
    )
    parser.add_argument(
        "--weeks", nargs="+", type=int, default=list(DEFAULT_WEEKS),
        help="Weeks to probe (default: %(default)s)",
    )
    parser.add_argument(
        "--league-types", nargs="+", choices=sorted(LEAGUE_TYPE_TO_INT),
        default=list(DEFAULT_LEAGUE_TYPES),
        help="League types (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.5,
        help="Pause between API calls to be polite (default: %(default)s s)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Markdown report path. Defaults to stdout.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    key_counts: Counter = Counter()
    samples: Dict[str, list] = defaultdict(list)
    grid_summary: List[dict] = []
    total_players = 0

    for season in args.seasons:
        for week in args.weeks:
            for lt in args.league_types:
                payload = _fetch(season, week, lt, args.timeout) or {}
                count = _scan(payload, key_counts, samples)
                grid_summary.append({
                    "season": season,
                    "week": week,
                    "league_type": lt,
                    "count": count,
                })
                total_players += count
                if args.sleep > 0:
                    time.sleep(args.sleep)

    report = _render_markdown(grid_summary, key_counts, samples, total_players)

    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"wrote {args.output} ({len(report)} bytes)")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
