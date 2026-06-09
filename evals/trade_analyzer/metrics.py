"""Pure scoring functions for the trade-analyzer eval harness."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from jsonschema import Draft202012Validator, ValidationError

from services.trade_analyzer.output_schema import TRADE_ANALYZER_JSON_SCHEMA

_BASE_GRADES = ("F", "D", "C", "B", "A")
_RATED_AGREE = frozenset({"agree", "disagree"})


def base_grade(grade: Optional[str]) -> Optional[str]:
    if not grade or not str(grade).strip():
        return None
    letter = str(grade).strip().upper()[0]
    return letter if letter in _BASE_GRADES else None


def grade_within_one(analyzer_grade: Optional[str], user_grade: Optional[str]) -> Optional[bool]:
    a = base_grade(analyzer_grade)
    u = base_grade(user_grade)
    if not a or not u:
        return None
    return abs(_BASE_GRADES.index(a) - _BASE_GRADES.index(u)) <= 1


def winner_accepted(agree_winner: str) -> Optional[bool]:
    if agree_winner == "agree":
        return True
    if agree_winner == "disagree":
        return False
    return None


def validate_structure(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    validator = Draft202012Validator(TRADE_ANALYZER_JSON_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return True, []
    return False, [e.message for e in errors]


def parse_response_json(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def summarize_feedback_rows(rows: Iterable[Any]) -> Dict[str, Any]:
    rated = [r for r in rows if getattr(r, "agree_winner", None) in _RATED_AGREE]
    acceptance_hits = 0
    grade_hits = 0
    grade_total = 0
    structural_hits = 0
    structural_total = 0
    details: List[Dict[str, Any]] = []

    for row in rated:
        response = parse_response_json(getattr(row, "response_json", None))
        accepted = winner_accepted(row.agree_winner)
        if accepted is True:
            acceptance_hits += 1

        grade_ok: Optional[bool] = None
        struct_ok = False
        struct_errors: List[str] = []
        if response is not None:
            structural_total += 1
            struct_ok, struct_errors = validate_structure(response)
            if struct_ok:
                structural_hits += 1
            user_grade = getattr(row, "user_grade", None)
            if user_grade:
                winner = response.get("winner")
                if winner == "side_a":
                    analyzer_grade = (response.get("side_a") or {}).get("trade_grade")
                elif winner == "side_b":
                    analyzer_grade = (response.get("side_b") or {}).get("trade_grade")
                else:
                    analyzer_grade = None
                grade_ok = grade_within_one(analyzer_grade, user_grade)
                if grade_ok is not None:
                    grade_total += 1
                    if grade_ok:
                        grade_hits += 1

        details.append({
            "id": getattr(row, "id", None),
            "agree_winner": row.agree_winner,
            "winner_accepted": accepted,
            "grade_within_one": grade_ok,
            "structural_valid": struct_ok,
            "structural_errors": struct_errors,
        })

    rated_n = len(rated)
    return {
        "rated_count": rated_n,
        "winner_acceptance_rate": (acceptance_hits / rated_n) if rated_n else None,
        "grade_within_one_rate": (grade_hits / grade_total) if grade_total else None,
        "grade_scored_count": grade_total,
        "structural_validity_rate": (
            structural_hits / structural_total if structural_total else None
        ),
        "structural_scored_count": structural_total,
        "details": details,
    }
