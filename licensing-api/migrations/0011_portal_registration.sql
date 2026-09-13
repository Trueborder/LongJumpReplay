-- Registration and profile completion for the customer portal.
-- Existing customer rows remain valid; accounts without a password/profile are
-- completed the next time they verify their email or sign in with OTP.
CREATE TABLE IF NOT EXISTS portal_profiles (
  customer_id TEXT PRIMARY KEY REFERENCES customers(id),
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  club_name TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS portal_registration_challenges (
  id TEXT PRIMARY KEY,
  customer_id TEXT REFERENCES customers(id),
  email TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  setup_token_hash TEXT,
  purpose TEXT NOT NULL CHECK (purpose IN ('registration', 'migration')),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  verified_at INTEGER,
  completed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_portal_registration_email_open
  ON portal_registration_challenges(email, purpose, completed_at, created_at);
CREATE INDEX IF NOT EXISTS idx_portal_registration_customer_open
  ON portal_registration_challenges(customer_id, purpose, completed_at, created_at);
CREATE INDEX IF NOT EXISTS idx_portal_registration_setup_token
  ON portal_registration_challenges(setup_token_hash, verified_at, completed_at);
