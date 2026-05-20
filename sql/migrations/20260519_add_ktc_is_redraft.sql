-- Dynasty and redraft KTC scrapes produce different ranks/values; store both per player.
-- Existing rows are treated as dynasty (is_redraft = false). Re-run KTC refresh for each mode after deploy.

ALTER TABLE player_ktc_oneqb_values
    ADD COLUMN IF NOT EXISTS is_redraft BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE player_ktc_superflex_values
    ADD COLUMN IF NOT EXISTS is_redraft BOOLEAN NOT NULL DEFAULT FALSE;

-- Drop legacy single-row-per-player assumption if a unique index existed only on player_id.
-- (Safe if index names differ; adjust manually in prod if migration fails.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_ktc_oneqb_values_player_redraft
    ON player_ktc_oneqb_values (player_id, is_redraft);

CREATE UNIQUE INDEX IF NOT EXISTS uq_player_ktc_superflex_values_player_redraft
    ON player_ktc_superflex_values (player_id, is_redraft);
