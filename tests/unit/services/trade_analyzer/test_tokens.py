"""Token estimation tests."""
from services.trade_analyzer.tokens import estimate_prompt_tokens


def test_estimate_prompt_tokens_minimum_one():
    usage = estimate_prompt_tokens("", "")
    assert usage["prompt_tokens_estimated"] >= 1


def test_estimate_prompt_tokens_scales_with_length():
    short = estimate_prompt_tokens("hi", "there")
    long = estimate_prompt_tokens("x" * 400, "y" * 400)
    assert long["prompt_tokens_estimated"] > short["prompt_tokens_estimated"]
