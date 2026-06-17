CREATE TABLE IF NOT EXISTS nfl_player_week_stats (
    id SERIAL PRIMARY KEY,
    season VARCHAR(4) NOT NULL,
    week INTEGER NOT NULL,
    player_id VARCHAR(20) NOT NULL,
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_updated TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_nfl_week_stats UNIQUE (season, week, player_id)
);
CREATE INDEX IF NOT EXISTS ix_nfl_week_stats_season ON nfl_player_week_stats (season, player_id);
CREATE INDEX IF NOT EXISTS ix_nfl_week_stats_season_week ON nfl_player_week_stats (season, week);

ALTER TABLE value_snapshots ADD COLUMN IF NOT EXISTS config_key VARCHAR(24);
CREATE INDEX IF NOT EXISTS ix_value_snapshots_config
  ON value_snapshots (player_id, source_key, league_format, config_key, metric_key, as_of);
