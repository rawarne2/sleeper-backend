"""Prompt size and structural invariants."""
from __future__ import annotations

from services.trade_analyzer.prompt import SYSTEM_PROMPT, build_user_prompt


def test_system_prompt_keeps_value_anchor_rule():
    """consensus_totals anchor rule is the highest-value guidance — never cut."""
    assert "consensus_totals" in SYSTEM_PROMPT
    assert "value_delta" in SYSTEM_PROMPT


def test_system_prompt_keeps_grade_guidance():
    assert "trade_grade" in SYSTEM_PROMPT
    # Allowed letter list must be present so model knows the valid set.
    assert "A+ A A-" in SYSTEM_PROMPT


def test_system_prompt_allows_low_grades_for_both_sides():
    """A trade can grade poorly for both teams when fit is wrong for everyone."""
    assert "Lose-lose" in SYSTEM_PROMPT or "lose-lose" in SYSTEM_PROMPT.lower()
    assert "BOTH sides" in SYSTEM_PROMPT or "both sides" in SYSTEM_PROMPT.lower()


def test_system_prompt_defines_starter_eligibility_by_rank_and_start_pct():
    """Starter-eligible requires high market_started_pct and position-specific rank bands."""
    assert "Starter-eligible" in SYSTEM_PROMPT
    assert "market_started_pct" in SYSTEM_PROMPT
    assert "positional_rank" in SYSTEM_PROMPT
    assert "starter-worthy ≤36" in SYSTEM_PROMPT  # WR flex demand
    assert "starter-worthy ≤12" in SYSTEM_PROMPT  # TE + 1qb QB
    assert "elite ≤6" in SYSTEM_PROMPT  # TE scarcity
    assert "`superflex`" in SYSTEM_PROMPT
    assert "starter-worthy ≤24" in SYSTEM_PROMPT


def test_system_prompt_keeps_contention_window_rule():
    assert "contention_window" in SYSTEM_PROMPT
    for window in ("rebuild", "now", "transition"):
        assert window in SYSTEM_PROMPT


def test_system_prompt_covers_pick_value_decay():
    """The model needs explicit guidance on multi-year pick discounting."""
    assert "pick" in SYSTEM_PROMPT.lower()
    assert "decay" in SYSTEM_PROMPT.lower() or "horizon" in SYSTEM_PROMPT.lower()


def test_system_prompt_covers_position_aging_curves():
    """Position-specific aging is the dynasty differentiator KTC under-prices."""
    for marker in ("aging", "prime", "RB", "WR", "TE", "QB"):
        assert marker in SYSTEM_PROMPT, f"missing aging-curve marker {marker!r}"


def test_system_prompt_covers_position_mate_awareness():
    assert "position-mate" in SYSTEM_PROMPT.lower() or "same position" in SYSTEM_PROMPT.lower()


def test_system_prompt_covers_injury_severity_hierarchy():
    """Severity ordering helps the model weight injuries correctly."""
    for marker in ("Out", "Doubtful", "Questionable"):
        assert marker in SYSTEM_PROMPT


def test_system_prompt_covers_redraft_override():
    """Redraft requires different pick valuation — make sure the model knows."""
    assert "redraft" in SYSTEM_PROMPT.lower()


def test_system_prompt_covers_tanking_posture():
    """User-supplied posture override; dynasty-only."""
    assert "posture" in SYSTEM_PROMPT
    assert "tanking" in SYSTEM_PROMPT
    assert "contending" in SYSTEM_PROMPT
    # Must explicitly skip tanking in redraft.
    assert "is_redraft=true" in SYSTEM_PROMPT


def test_system_prompt_keeps_narrative_quality_guidance():
    """Without explicit anti-recap guidance the model restates the UI."""
    assert "non-obvious" in SYSTEM_PROMPT
    assert "summary_bullets" in SYSTEM_PROMPT
    assert "summary_bullets" in SYSTEM_PROMPT


def test_user_prompt_includes_additional_context():
    out = build_user_prompt({"trade": {}, "side_a": {}, "side_b": {}}, "trade for win-now")
    assert "ADDITIONAL USER CONTEXT" in out
    assert "trade for win-now" in out


def test_user_prompt_handles_none_additional_context():
    out = build_user_prompt({"trade": {}}, None)
    assert "ADDITIONAL USER CONTEXT" in out
    assert "(none)" in out


def test_user_prompt_includes_retrieved_context_before_additional():
    from services.trade_analyzer.rag.retrieve import RetrievedChunk

    chunks = [RetrievedChunk("strategy_kb", "grading", "Grade against fit", 0.8)]
    out = build_user_prompt({"trade": {}}, "notes", retrieved=chunks)
    assert out.index("RETRIEVED CONTEXT") < out.index("ADDITIONAL USER CONTEXT")
    assert "[strategy_kb/grading]" in out
    assert "notes" in out


def test_user_prompt_omits_retrieved_when_empty():
    out = build_user_prompt({"trade": {}}, None, retrieved=[])
    assert "RETRIEVED CONTEXT" not in out
