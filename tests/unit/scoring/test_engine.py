from services.scoring.engine import score_stat_line


def test_reproduces_sleeper_points_for_te_with_tep():
    scoring = {"rec_yd": 0.1, "rec": 0.5, "bonus_rec_te": 0.5, "rec_td": 6.0}
    stats = {"rec_yd": 59.0, "rec": 7.0, "bonus_rec_te": 7.0}  # bonus_rec_te = TE receptions
    assert score_stat_line(scoring, stats) == 12.9  # matches Sleeper matchup players_points


def test_ignores_non_numeric_and_missing_keys():
    assert score_stat_line({"rec": 1.0, "x": 2.0}, {"rec": 3.0, "pos_rank_ppr": "WR1"}) == 3.0
    assert score_stat_line({}, {"rec": 5.0}) == 0.0
