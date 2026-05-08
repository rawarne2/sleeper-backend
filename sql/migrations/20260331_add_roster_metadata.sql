-- Add column for Sleeper roster.metadata JSON (fixes prior save path that used invalid attribute name "metadata").
-- Run against existing Postgres DBs; safe to run once.

ALTER TABLE sleeper_rosters
  ADD COLUMN IF NOT EXISTS roster_metadata TEXT;
