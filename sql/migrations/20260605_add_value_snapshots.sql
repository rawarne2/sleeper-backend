-- sql/migrations/20260605_add_value_snapshots.sql
CREATE TABLE IF NOT EXISTS value_snapshots (
  id            SERIAL PRIMARY KEY,
  player_id     INTEGER REFERENCES players(id),
  pick_key      VARCHAR(40),
  source_key    VARCHAR(30)  NOT NULL,
  league_format VARCHAR(20)  NOT NULL,
  metric_key    VARCHAR(30)  NOT NULL,
  metric_value  DOUBLE PRECISION,
  rank          INTEGER,
  as_of         TIMESTAMP    NOT NULL,
  raw_json      TEXT
);
CREATE INDEX IF NOT EXISTS ix_value_snapshots_player ON value_snapshots(player_id);
CREATE INDEX IF NOT EXISTS ix_value_snapshots_pick   ON value_snapshots(pick_key);
CREATE INDEX IF NOT EXISTS ix_value_snapshots_source ON value_snapshots(source_key);
CREATE INDEX IF NOT EXISTS ix_value_snapshots_latest
  ON value_snapshots(player_id, source_key, league_format, metric_key, as_of);

CREATE TABLE IF NOT EXISTS value_sources (
  source_key      VARCHAR(30) PRIMARY KEY,
  display_name    VARCHAR(80) NOT NULL,
  kind            VARCHAR(20) NOT NULL,
  attribution_url VARCHAR(200),
  last_synced_at  TIMESTAMP
);
