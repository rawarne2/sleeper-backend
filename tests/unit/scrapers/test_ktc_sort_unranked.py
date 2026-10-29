from scrapers.pipelines import scrape_and_process_data


class _FakeScraper:
    @staticmethod
    def scrape_ktc(is_redraft):
        return [
            {"player_name": "Unranked", "superflex_values": {"rank": None}, "oneqb_values": {"rank": None}},
            {"player_name": "Second", "superflex_values": {"rank": 2}, "oneqb_values": {"rank": 2}},
            {"player_name": "First", "superflex_values": {"rank": 1}, "oneqb_values": {"rank": 1}},
        ]


def test_unranked_players_sort_last_instead_of_failing():
    for fmt in ("superflex", "1qb"):
        players, err = scrape_and_process_data(_FakeScraper, fmt, False, "tep", sleeper_players=[])
        assert err is None
        assert [p["player_name"] for p in players] == ["First", "Second", "Unranked"]
