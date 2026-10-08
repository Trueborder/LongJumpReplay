-- Independent Minecraft accounts. IDs and password hashes are copied without changes.

CREATE TABLE customers (
  id                 TEXT PRIMARY KEY,
  email              TEXT NOT NULL,
  stripe_customer_id TEXT,
  created_at         INTEGER NOT NULL,
  updated_at         INTEGER NOT NULL
);

CREATE UNIQUE INDEX idx_customers_email ON customers (email);

CREATE INDEX idx_customers_stripe ON customers (stripe_customer_id);

CREATE TABLE portal_sessions (
  id          TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers (id),
  token_hash  TEXT NOT NULL UNIQUE,
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  revoked_at  INTEGER
, csrf_token_hash TEXT);

CREATE INDEX idx_portal_sessions_customer ON portal_sessions (customer_id, revoked_at);

CREATE INDEX idx_portal_sessions_open ON portal_sessions (token_hash, revoked_at, expires_at);

CREATE TABLE portal_login_codes (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL REFERENCES customers (id),
  email         TEXT NOT NULL,
  code_hash     TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  expires_at    INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  used_at       INTEGER
, purpose TEXT NOT NULL DEFAULT 'portal'
  CHECK (purpose IN ('portal', 'activation')));

CREATE INDEX idx_portal_codes_email_open
  ON portal_login_codes (email, used_at, created_at);

CREATE INDEX idx_portal_codes_customer_open
  ON portal_login_codes (customer_id, used_at);

CREATE INDEX idx_portal_codes_purpose_email_open
  ON portal_login_codes (purpose, email, used_at, created_at);

CREATE TABLE customer_password_credentials (
  customer_id TEXT PRIMARY KEY REFERENCES customers(id),
  password_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  password_changed_at INTEGER NOT NULL
);

CREATE TABLE password_reset_codes (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  email TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  used_at INTEGER
);

CREATE INDEX idx_password_reset_codes_email_open
  ON password_reset_codes(email, used_at, created_at);

CREATE INDEX idx_password_reset_codes_customer_open
  ON password_reset_codes(customer_id, used_at, created_at);

CREATE TABLE portal_profiles (
  customer_id TEXT PRIMARY KEY REFERENCES customers(id),
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  club_name TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE portal_registration_challenges (
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

CREATE INDEX idx_portal_registration_email_open
  ON portal_registration_challenges(email, purpose, completed_at, created_at);

CREATE INDEX idx_portal_registration_customer_open
  ON portal_registration_challenges(customer_id, purpose, completed_at, created_at);

CREATE INDEX idx_portal_registration_setup_token
  ON portal_registration_challenges(setup_token_hash, verified_at, completed_at);

CREATE TABLE privacy_requests (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  type TEXT NOT NULL CHECK(type IN ('export','deletion')),
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','completed','rejected')),
  created_at INTEGER NOT NULL,
  completed_at INTEGER,
  detail TEXT
);

CREATE INDEX idx_privacy_requests_customer ON privacy_requests(customer_id,created_at);

CREATE TABLE rate_limits (
  bucket     TEXT PRIMARY KEY,
  count      INTEGER NOT NULL,
  window_start INTEGER NOT NULL
);

CREATE TABLE events (
  id         TEXT PRIMARY KEY,
  license_id TEXT,
  type       TEXT NOT NULL,
  detail     TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_events_license ON events (license_id, created_at);

CREATE INDEX idx_events_type ON events (type, created_at);
