from managers.database_manager import DatabaseManager
from models.entities import NflPlayerWeekStats
from models.extensions import db
from sqlalchemy import select


def test_save_nfl_week_stats_upserts(app_context):
    raw = {"7553": {"rec": 7.0, "rec_yd": 59.0, "bonus_rec_te": 7.0, "gp": 1.0},
           "INVALID": "not-a-dict"}
    DatabaseManager.save_nfl_week_stats("2025", 1, raw)
    row = db.session.execute(select(NflPlayerWeekStats).filter_by(season="2025", week=1, player_id="7553")).scalars().first()
    assert row is not None and row.stats["rec"] == 7.0
    # upsert overwrites
    DatabaseManager.save_nfl_week_stats("2025", 1, {"7553": {"rec": 9.0, "gp": 1.0}})
    row2 = db.session.execute(select(NflPlayerWeekStats).filter_by(season="2025", week=1, player_id="7553")).scalars().first()
    assert row2.stats["rec"] == 9.0
