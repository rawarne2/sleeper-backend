from scrapers.ktc_scraper import KTCScraper

PLAYERS = '[{"playerName":"Jahmyr Gibbs","playerID":1415},{"playerName":"A;B]","playerID":2}]'


def test_extracts_from_ktc_players_json_script():
    html = (
        '<body>\n    <script type="application/json" id="ktc-players">' + PLAYERS + '</script>\n'
        "<script>\n    var playersArray = JSON.parse(document.getElementById('ktc-players').textContent);\n"
        '    var oneQBPlayers = [{"playerName":"Other","playerID":9}];\n</script>'
    )
    players = KTCScraper.extract_players_array(html)
    assert [p["playerID"] for p in players] == [1415, 2]


def test_extracts_legacy_inline_players_array():
    html = "<script>var playersArray = " + PLAYERS + ";\nvar x = 1;</script>"
    assert [p["playerID"] for p in KTCScraper.extract_players_array(html)] == [1415, 2]


def test_missing_players_returns_empty():
    assert KTCScraper.extract_players_array("<html><body>nothing</body></html>") == []
