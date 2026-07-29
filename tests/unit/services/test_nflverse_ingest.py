# tests/unit/services/test_nflverse_ingest.py
from datetime import datetime, UTC
from unittest.mock import patch

from sqlalchemy import select

from models.entities import Player, PlayerInjuryReport
from models.extensions import db
from services import nflverse_ingest


def _sample_rows():
    return [
        {"gsis_id": "00-0034796", "season": "2025", "week": "3",
         "report_status": "Questionable", "report_primary_injury": "Knee",
         "practice_status": "Limited Participation in Practice"},
        {"gsis_id": "00-0034796", "season": "2025", "week": "5",
         "report_status": "Out", "report_primary_injury": "Ankle",
         "report_secondary_injury": "", "practice_status": "Did Not Participate In Practice"},
        {"gsis_id": "unknown-id", "season": "2025", "week": "5", "report_status": "Out"},
    ]


def test_ingest_stores_latest_week_and_resolves_by_gsis(app_context):
    db.session.add(Player(
        player_name="Josh Allen", position="QB", team="BUF", match_key="joshallen-QB",
        sleeper_player_id="4984", gsis_id="00-0034796", last_updated=datetime.now(UTC),
    ))
    db.session.commit()

    with patch("services.nflverse_ingest._fetch_csv", return_value=_sample_rows()):
        result = nflverse_ingest.ingest_nflverse_injuries("2025", session=db.session)

    assert result["week"] == 5
    assert result["saved"] == 1
    assert result["skipped"] == 1  # unknown gsis dropped

    rows = db.session.execute(select(PlayerInjuryReport)).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.week == 5 and row.report_status == "Out"
    assert row.report_primary_injury == "Ankle"
    assert row.report_secondary_injury is None  # empty string cleaned to None


def test_reingest_updates_in_place(app_context):
    db.session.add(Player(
        player_name="Josh Allen", position="QB", team="BUF", match_key="joshallen-QB",
        sleeper_player_id="4984", gsis_id="00-0034796", last_updated=datetime.now(UTC),
    ))
    db.session.commit()

    with patch("services.nflverse_ingest._fetch_csv", return_value=_sample_rows()):
        nflverse_ingest.ingest_nflverse_injuries("2025", session=db.session)
        result2 = nflverse_ingest.ingest_nflverse_injuries("2025", session=db.session)

    assert result2["updated"] == 1 and result2["saved"] == 0
    assert db.session.execute(select(PlayerInjuryReport)).scalars().all().__len__() == 1
