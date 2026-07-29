# tests/unit/services/test_news_ingest.py
from datetime import datetime, UTC
from unittest.mock import patch

from sqlalchemy import select

from models.entities import Player, PlayerNews
from models.extensions import db
from services import news_ingest


def _news_items():
    return [
        {"title": "Allen questionable", "link": "https://ex.com/a",
         "image": "https://ex.com/a.png", "playerID": ["3121"]},
        {"title": "General league news", "link": "https://ex.com/general", "playerID": []},
        {"title": "", "link": "https://ex.com/empty", "playerID": ["3121"]},  # no title -> skip
    ]


def test_skipped_without_key(app_context):
    with patch("scrapers.tank01_client.is_configured", return_value=False):
        result = news_ingest.ingest_player_news(session=db.session)
    assert "skipped" in result


def test_ingest_stores_player_linked_news_only(app_context):
    db.session.add(Player(
        player_name="Josh Allen", position="QB", team="BUF", match_key="joshallen-QB",
        sleeper_player_id="4984", last_updated=datetime.now(UTC),
    ))
    db.session.commit()

    with patch("scrapers.tank01_client.is_configured", return_value=True), \
         patch("scrapers.tank01_client.get_news", return_value=_news_items()), \
         patch("scrapers.tank01_client.sleeper_id_by_tank_id", return_value={"3121": "4984"}):
        result = news_ingest.ingest_player_news(session=db.session)

    assert result["saved"] == 1  # only the player-linked, titled item
    rows = db.session.execute(select(PlayerNews)).scalars().all()
    assert len(rows) == 1
    assert rows[0].headline == "Allen questionable"
    assert rows[0].url == "https://ex.com/a"


def test_reingest_dedupes_by_url_and_player(app_context):
    db.session.add(Player(
        player_name="Josh Allen", position="QB", team="BUF", match_key="joshallen-QB",
        sleeper_player_id="4984", last_updated=datetime.now(UTC),
    ))
    db.session.commit()

    with patch("scrapers.tank01_client.is_configured", return_value=True), \
         patch("scrapers.tank01_client.get_news", return_value=_news_items()), \
         patch("scrapers.tank01_client.sleeper_id_by_tank_id", return_value={"3121": "4984"}):
        news_ingest.ingest_player_news(session=db.session)
        result2 = news_ingest.ingest_player_news(session=db.session)

    assert result2["saved"] == 0
    assert len(db.session.execute(select(PlayerNews)).scalars().all()) == 1
