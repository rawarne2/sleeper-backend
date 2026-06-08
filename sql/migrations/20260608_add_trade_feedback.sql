-- sql/migrations/20260608_add_trade_feedback.sql
CREATE TABLE IF NOT EXISTS trade_feedback (
  id                VARCHAR(36) PRIMARY KEY,
  client_id         VARCHAR(64),
  league_id         VARCHAR(20),
  provider          VARCHAR(40),
  model             VARCHAR(80),
  request_json      TEXT,
  context_json      TEXT,
  response_json     TEXT,
  agree_winner      VARCHAR(12) NOT NULL,
  user_grade        VARCHAR(2),
  note              TEXT,
  context_available BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMP NOT NULL,
  feedback_at       TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_trade_feedback_client ON trade_feedback(client_id);
CREATE INDEX IF NOT EXISTS ix_trade_feedback_league ON trade_feedback(league_id);
CREATE INDEX IF NOT EXISTS ix_trade_feedback_agree  ON trade_feedback(agree_winner);
