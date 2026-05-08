CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_players_sleeper_player_id
  ON players (sleeper_player_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sleeper_weekly_season_lt_week
  ON sleeper_weekly_data (season, league_type, week);

-- Dashboard ownership slice: max week subquery + per-player filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sleeper_weekly_season_lt_week_player
  ON sleeper_weekly_data (season, league_type, week, player_id);

-- Dashboard roster player slice: join players -> format-specific KTC row by player.id
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_player_ktc_oneqb_values_player_id
  ON player_ktc_oneqb_values (player_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_player_ktc_superflex_values_player_id
  ON player_ktc_superflex_values (player_id);
