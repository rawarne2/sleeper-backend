import scrapers
from scrapers import SleeperScraper


def test_fetch_players_research_normalizes_string_league_type(monkeypatch):
    requested_urls = []

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'players': []}

    def mock_get(url, **kwargs):
        requested_urls.append(url)
        return MockResponse()

    monkeypatch.setattr(scrapers.requests, 'get', mock_get)

    result = SleeperScraper.fetch_players_research(
        '2024', week=1, league_type='dynasty')

    assert result == {'players': []}
    assert requested_urls
    assert requested_urls[0].endswith('league_type=2')
