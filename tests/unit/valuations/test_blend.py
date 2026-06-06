# tests/unit/valuations/test_blend.py
from services.valuations.blend import normalize_min_max, blend_values


def test_normalize_min_max_scales_to_0_10000():
    out = normalize_min_max({"a": 10.0, "b": 5.0, "c": 0.0})
    assert out["a"] == 10000.0
    assert out["c"] == 0.0
    assert out["b"] == 5000.0


def test_normalize_handles_flat_set():
    out = normalize_min_max({"a": 7.0, "b": 7.0})
    assert out == {"a": 5000.0, "b": 5000.0}


def test_blend_weighted_average_after_normalization():
    per_source = {
        "ktc": {"a": 10000.0, "b": 0.0},          # already scaled
        "fantasycalc": {"a": 100.0, "b": 50.0},   # different scale -> normalized: a=10000,b=0
    }
    out = blend_values(per_source, weights={"ktc": 0.5, "fantasycalc": 0.5})
    assert out["a"] == 10000.0
    assert out["b"] == 0.0


def test_blend_skips_missing_source_for_asset():
    per_source = {"ktc": {"a": 10.0, "b": 5.0}, "fantasycalc": {"a": 8.0}}
    out = blend_values(per_source, weights={"ktc": 1.0, "fantasycalc": 1.0})
    # b only present in ktc -> equals ktc-normalized b (0.0)
    assert out["b"] == 0.0
    assert out["a"] is not None
