"""SleeperScraper.fetch_traded_picks + scrape_league_data integration."""
from unittest.mock import MagicMock, patch

from scrapers.sleeper_scraper import SleeperScraper


def _ok(payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    r.raise_for_status = lambda: None
    return r


def test_fetch_traded_picks_returns_list(traded_picks_fixture):
    with patch("scrapers.sleeper_scraper.requests.get",
               return_value=_ok(traded_picks_fixture)):
        result = SleeperScraper.fetch_traded_picks("123")
    assert isinstance(result, list)
    assert result[0]["round"] == 1


def test_fetch_traded_picks_returns_none_on_error():
    import requests
    with patch("scrapers.sleeper_scraper.requests.get",
               side_effect=requests.RequestException("nope")):
        result = SleeperScraper.fetch_traded_picks("bad")
    assert result is None


def test_scrape_league_data_includes_traded_picks(traded_picks_fixture):
    league_info = {"league_id": "abc", "name": "X", "season": "2026"}
    with patch.object(SleeperScraper, "fetch_league_info", return_value=league_info), \
         patch.object(SleeperScraper, "fetch_league_rosters", return_value=[]), \
         patch.object(SleeperScraper, "fetch_league_users", return_value=[]), \
         patch.object(SleeperScraper, "fetch_traded_picks", return_value=traded_picks_fixture):
        result = SleeperScraper.scrape_league_data("abc")
    assert result["success"] is True
    assert result["traded_picks"] == traded_picks_fixture


def test_scrape_league_data_treats_picks_failure_as_warning():
    league_info = {"league_id": "abc", "name": "X", "season": "2026"}
    with patch.object(SleeperScraper, "fetch_league_info", return_value=league_info), \
         patch.object(SleeperScraper, "fetch_league_rosters", return_value=[]), \
         patch.object(SleeperScraper, "fetch_league_users", return_value=[]), \
         patch.object(SleeperScraper, "fetch_traded_picks", return_value=None):
        result = SleeperScraper.scrape_league_data("abc")
    assert result["success"] is True
    assert result["traded_picks"] == []
