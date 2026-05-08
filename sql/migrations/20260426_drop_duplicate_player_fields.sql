-- Drop duplicated KTC fields now that Sleeper is the single source of truth for
-- player height and birth date.
--
-- Sleeper's `height` (e.g. `6'5"`) and `birth_date` (ISO date) replace the
-- KTC `heightFeet`, `heightInches`, and `birthday` columns.
--
-- Run with: psql "$DATABASE_URL" -f sql/migrations/20260426_drop_duplicate_player_fields.sql

ALTER TABLE players DROP COLUMN IF EXISTS "heightFeet";
ALTER TABLE players DROP COLUMN IF EXISTS "heightInches";
ALTER TABLE players DROP COLUMN IF EXISTS birthday;
