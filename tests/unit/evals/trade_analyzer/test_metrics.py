"""Eval harness metric unit tests."""
from __future__ import annotations

import json

from evals.trade_analyzer.metrics import (
    grade_within_one,
    summarize_feedback_rows,
    validate_structure,
    winner_accepted,
)
from tests.fixtures.trade_analyzer import _load


def test_winner_accepted_mapping():
    assert winner_accepted("agree") is True
    assert winner_accepted("disagree") is False
    assert winner_accepted("unsure") is None


def test_grade_within_one_allows_adjacent_letters():
    assert grade_within_one("B+", "C") is True
    assert grade_within_one("A", "C") is False
    assert grade_within_one(None, "B") is None


def test_validate_structure_accepts_echo_fixture():
    payload = _load("trade_analyzer_echo.json")
    ok, errors = validate_structure(payload)
    assert ok is True
    assert errors == []


def test_validate_structure_rejects_missing_value_delta():
    bad = {
        "winner": "even",
        "summary_bullets": ["a", "b"],
        "side_a": {"trade_grade": "C", "pros": [], "cons": []},
        "side_b": {"trade_grade": "C", "pros": [], "cons": []},
    }
    ok, errors = validate_structure(bad)
    assert ok is False
    assert errors


class _Row:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_summarize_feedback_rows_computes_rates():
    response = _load("trade_analyzer_echo.json")
    rows = [
        _Row(
            id="1",
            agree_winner="agree",
            user_grade="B",
            response_json=json.dumps(response),
        ),
        _Row(
            id="2",
            agree_winner="disagree",
            user_grade="A",
            response_json=json.dumps(response),
        ),
    ]
    summary = summarize_feedback_rows(rows)
    assert summary["rated_count"] == 2
    assert summary["winner_acceptance_rate"] == 0.5
    assert summary["structural_validity_rate"] == 1.0
