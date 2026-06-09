"""Orchestrate trade-analyzer eval modes and write JSON reports."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from evals.trade_analyzer.metrics import (
    parse_response_json,
    summarize_feedback_rows,
    validate_structure,
)

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _ROOT / "tests" / "fixtures" / "data"
_GOLD_SET = Path(__file__).resolve().parent / "gold_set.json"
_DEFAULT_OUT = Path(__file__).resolve().parent / "results"


def _load_fixture(name: str) -> Dict[str, Any]:
    path = _FIXTURES / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def run_structural_eval() -> Dict[str, Any]:
    echo = _load_fixture("trade_analyzer_echo.json")
    ok, errors = validate_structure(echo)
    return {
        "mode": "structural",
        "cases": [{
            "id": "trade_analyzer_echo.json",
            "structural_valid": ok,
            "errors": errors,
        }],
        "structural_validity_rate": 1.0 if ok else 0.0,
        "structural_scored_count": 1,
    }


def run_feedback_eval() -> Dict[str, Any]:
    from sqlalchemy.exc import ProgrammingError

    from app import app
    from models.entities import TradeFeedback

    with app.app_context():
        try:
            rows = (
                TradeFeedback.query
                .filter(TradeFeedback.context_available.is_(True))
                .filter(TradeFeedback.agree_winner.in_(("agree", "disagree", "unsure")))
                .all()
            )
        except ProgrammingError as exc:
            return {
                "mode": "feedback",
                "error": "trade_feedback table unavailable — apply migration 20260608",
                "details": str(exc.orig) if getattr(exc, "orig", None) else str(exc),
                "rated_count": 0,
                "total_rows": 0,
                "winner_acceptance_rate": None,
                "grade_within_one_rate": None,
                "structural_validity_rate": None,
            }
        summary = summarize_feedback_rows(rows)
    summary["mode"] = "feedback"
    summary["total_rows"] = len(rows)
    return summary


def _run_live_echo_case(case: Dict[str, Any], league_fixture: Dict[str, Any]) -> Dict[str, Any]:
    from app import app
    from services.trade_analyzer.analyzer import run_analysis

    req = dict(case["request"])
    outcome = None
    with app.app_context(), patch(
        "services.trade_analyzer.analyzer.load_league_bundle",
        return_value=league_fixture,
    ), patch(
        "services.trade_analyzer.context.compute_owned_picks",
        return_value={},
    ):
        outcome = run_analysis(
            req,
            provider_name=req.get("provider") or "echo",
            model=req.get("model") or "echo",
            timeout_s=60,
        )
    body = outcome.body if outcome else {}
    ok, errors = validate_structure(body) if outcome and outcome.status_code == 200 else (False, ["non-200"])
    winner_match = (
        body.get("winner") == case.get("expected_winner")
        if outcome and outcome.status_code == 200
        else False
    )
    return {
        "id": case["id"],
        "status_code": outcome.status_code if outcome else 500,
        "structural_valid": ok,
        "structural_errors": errors,
        "expected_winner": case.get("expected_winner"),
        "actual_winner": body.get("winner"),
        "winner_match": winner_match,
    }


def run_gold_eval(*, league_fixture: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _GOLD_SET.open(encoding="utf-8") as fh:
        gold = json.load(fh)

    cases_out: List[Dict[str, Any]] = []
    winner_hits = 0
    winner_total = 0
    structural_hits = 0
    structural_total = 0

    for case in gold.get("cases") or []:
        kind = case.get("kind")
        if kind == "fixture":
            payload = _load_fixture(case["fixture"])
            ok, errors = validate_structure(payload)
            row = {
                "id": case["id"],
                "kind": kind,
                "structural_valid": ok,
                "structural_errors": errors,
            }
            structural_total += 1
            if ok:
                structural_hits += 1
            cases_out.append(row)
        elif kind == "live_echo":
            if league_fixture is None:
                league_fixture = _load_fixture("trade_analyzer_league.json")
            row = _run_live_echo_case(case, league_fixture)
            row["kind"] = kind
            cases_out.append(row)
            if row["status_code"] == 200:
                structural_total += 1
                if row["structural_valid"]:
                    structural_hits += 1
                if case.get("expected_winner"):
                    winner_total += 1
                    if row["winner_match"]:
                        winner_hits += 1
        else:
            cases_out.append({"id": case.get("id"), "error": f"unknown kind {kind!r}"})

    return {
        "mode": "gold",
        "cases": cases_out,
        "gold_winner_match_rate": (winner_hits / winner_total) if winner_total else None,
        "gold_winner_scored_count": winner_total,
        "structural_validity_rate": (
            structural_hits / structural_total if structural_total else None
        ),
        "structural_scored_count": structural_total,
    }


def run_all_eval() -> Dict[str, Any]:
    return {
        "modes": {
            "structural": run_structural_eval(),
            "feedback": run_feedback_eval(),
            "gold": run_gold_eval(),
        }
    }


def _print_summary(report: Dict[str, Any]) -> None:
    if "modes" in report:
        for name, block in report["modes"].items():
            _print_block(name, block)
        return
    _print_block(report.get("mode", "eval"), report)


def _print_block(label: str, block: Dict[str, Any]) -> None:
    print(f"\n== {label} ==")
    for key in (
        "rated_count",
        "total_rows",
        "winner_acceptance_rate",
        "grade_within_one_rate",
        "grade_scored_count",
        "structural_validity_rate",
        "structural_scored_count",
        "gold_winner_match_rate",
        "gold_winner_scored_count",
    ):
        if key in block and block[key] is not None:
            val = block[key]
            if isinstance(val, float):
                print(f"  {key}: {val:.3f}")
            else:
                print(f"  {key}: {val}")


def write_report(report: Dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"eval-{stamp}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    return path


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Trade analyzer eval harness")
    parser.add_argument(
        "--mode",
        choices=("structural", "feedback", "gold", "all"),
        default="all",
    )
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = parser.parse_args(argv)

    if args.mode == "structural":
        report = run_structural_eval()
    elif args.mode == "feedback":
        report = run_feedback_eval()
    elif args.mode == "gold":
        report = run_gold_eval()
    else:
        report = run_all_eval()

    report["generated_at"] = datetime.now(UTC).isoformat()
    path = write_report(report, args.out)
    _print_summary(report)
    print(f"\nWrote {path}")
    return 0
