"""Pytest plugin: trade-analyzer JSON fixtures."""
import json
import pathlib

import pytest

_DATA = pathlib.Path(__file__).parent / "data"


def _load(name: str):
    with (_DATA / name).open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def echo_fixture():
    return _load("trade_analyzer_echo.json")


@pytest.fixture
def league_fixture():
    return _load("trade_analyzer_league.json")


@pytest.fixture
def traded_picks_fixture():
    return _load("trade_analyzer_traded_picks.json")
