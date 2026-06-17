# tests/unit/valuations/test_fantasycalc_config_key.py
from services.valuations.sources.fantasycalc import _config_key


def test_config_key_format():
    assert _config_key(12, 2, 0.5) == "12-2-0.5"
    assert _config_key(10, 1, 1.0) == "10-1-1.0"
