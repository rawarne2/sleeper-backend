-- value_snapshots: drop indexes that are prefixes of ix_value_snapshots_config or unused.
-- ix_value_snapshots_config (player_id, source_key, league_format, config_key, metric_key, as_of) stays.
-- Run outside a transaction block (CONCURRENTLY). Idempotent.
DROP INDEX CONCURRENTLY IF EXISTS ix_value_snapshots_player_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_value_snapshots_source_key;
DROP INDEX CONCURRENTLY IF EXISTS ix_value_snapshots_pick_key;
DROP INDEX CONCURRENTLY IF EXISTS ix_value_snapshots_config_key;
DROP INDEX CONCURRENTLY IF EXISTS ix_value_snapshots_latest;
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_value_snapshots_config
  ON value_snapshots (player_id, source_key, league_format, config_key, metric_key, as_of);
