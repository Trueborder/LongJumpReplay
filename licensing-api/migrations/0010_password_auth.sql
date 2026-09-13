-- Optional portal passwords. OTP remains available as the recovery method.
ALTER TABLE portal_sessions ADD COLUMN csrf_token_hash TEXT;

CREATE TABLE IF NOT EXISTS customer_password_credentials (
  customer_id TEXT PRIMARY KEY REFERENCES customers(id),
  password_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  password_changed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_codes (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  email TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  used_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_password_reset_codes_email_open
  ON password_reset_codes(email, used_at, created_at);
CREATE INDEX IF NOT EXISTS idx_password_reset_codes_customer_open
  ON password_reset_codes(customer_id, used_at, created_at);
