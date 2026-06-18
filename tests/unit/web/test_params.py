import pytest

from web.errors import ApiError
from web.params import validate_ktc_params


def test_valid_params_normalize():
    p = validate_ktc_params("TRUE", "SuperFlex", "tep")
    assert p.is_redraft is True
    assert p.league_format == "superflex"
    assert p.tep_level == "tep"


def test_empty_tep_is_none():
    assert validate_ktc_params("false", "1qb", "").tep_level is None


@pytest.mark.parametrize("ir,lf,tep,msg", [
    ("maybe", "1qb", "", "is_redraft"),
    ("false", "2qb", "", "league_format"),
    ("false", "1qb", "tepX", "tep_level"),
])
def test_invalid_params_raise_apierror(ir, lf, tep, msg):
    with pytest.raises(ApiError) as ei:
        validate_ktc_params(ir, lf, tep)
    assert msg in str(ei.value.message)
    assert ei.value.status_code == 400
