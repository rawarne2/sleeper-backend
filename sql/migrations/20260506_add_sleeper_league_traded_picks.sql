-- sql/migrations/20260506_add_sleeper_league_traded_picks.sql
ALTER TABLE sleeper_leagues
  ADD COLUMN IF NOT EXISTS traded_picks TEXT;
