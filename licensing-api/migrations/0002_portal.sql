-- Customer portal authentication and billing sessions.
-- Verification codes are scoped so a portal login code can never be exchanged
-- for a desktop activation grant.

ALTER TABLE verification_codes ADD COLUMN purpose TEXT NOT NULL DEFAULT 'activation';
CREATE INDEX idx_codes_purpose_email ON verification_codes (purpose, email, created_at);

CREATE TABLE portal_sessions (
  id          TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers (id),
  token_hash  TEXT NOT NULL UNIQUE,
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  revoked_at  INTEGER
);

CREATE INDEX idx_portal_sessions_customer ON portal_sessions (customer_id, revoked_at);
CREATE INDEX idx_portal_sessions_open ON portal_sessions (token_hash, revoked_at, expires_at);
