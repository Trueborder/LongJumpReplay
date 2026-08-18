-- Portal access belongs to a verified email address, not to a licence.
-- Keeping portal codes separate prevents an account-only code from ever being
-- exchanged for a desktop activation grant.
CREATE TABLE portal_login_codes (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL REFERENCES customers (id),
  email         TEXT NOT NULL,
  code_hash     TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  expires_at    INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  used_at       INTEGER
);

CREATE INDEX idx_portal_codes_email_open
  ON portal_login_codes (email, used_at, created_at);
CREATE INDEX idx_portal_codes_customer_open
  ON portal_login_codes (customer_id, used_at);
