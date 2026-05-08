-- One-time cleanup: remove rows that should not be in `players`.
-- match_key must be set; search_rank 9999999 is Sleeper's non-rosterable sentinel.
-- Run in Supabase SQL editor or: psql "$DATABASE_URL" -f this file
--
-- Preview:
-- SELECT id, player_name, position, match_key, search_rank FROM players
--   WHERE match_key IS NULL OR match_key = '' OR search_rank = 9999999;

DELETE FROM player_ktc_oneqb_values
WHERE player_id IN (
  SELECT id FROM players
  WHERE match_key IS NULL OR match_key = '' OR search_rank = 9999999
);

DELETE FROM player_ktc_superflex_values
WHERE player_id IN (
  SELECT id FROM players
  WHERE match_key IS NULL OR match_key = '' OR search_rank = 9999999
);

DELETE FROM players
WHERE match_key IS NULL OR match_key = '' OR search_rank = 9999999;
