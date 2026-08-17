-- LongJumpReplay licensing schema.
--
-- Data minimisation: the only personal data stored is the email address the
-- customer used at checkout, which is required to deliver verification codes.
-- Devices are recorded as an opaque identifier derived on the customer's
-- machine; no raw hardware identifiers, computer names or locations are stored.

CREATE TABLE customers (
  id                 TEXT PRIMARY KEY,
  email              TEXT NOT NULL,
  stripe_customer_id TEXT,
  created_at         INTEGER NOT NULL,
  updated_at         INTEGER NOT NULL
);

-- Email is the activation identifier, so lookups must be exact and unique.
-- Addresses are lowercased before insert.
CREATE UNIQUE INDEX idx_customers_email ON customers (email);
CREATE INDEX idx_customers_stripe ON customers (stripe_customer_id);

CREATE TABLE licenses (
  id                     TEXT PRIMARY KEY,
  customer_id            TEXT NOT NULL REFERENCES customers (id),
  product                TEXT NOT NULL DEFAULT 'LongJumpReplay',
  type                   TEXT NOT NULL CHECK (type IN ('lifetime', 'subscription')),
  status                 TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'expired', 'suspended')),
  max_devices            INTEGER NOT NULL,
  stripe_customer_id     TEXT,
  stripe_subscription_id TEXT,
  stripe_price_id        TEXT,
  -- For subscriptions: when the paid period ends. A lapsed subscription stays
  -- usable until this plus the configured grace period, so a card that fails on
  -- a Friday does not kill a Saturday competition.
  current_period_end     INTEGER,
  created_at             INTEGER NOT NULL,
  updated_at             INTEGER NOT NULL,
  last_stripe_sync       INTEGER
);

CREATE INDEX idx_licenses_customer ON licenses (customer_id);
CREATE UNIQUE INDEX idx_licenses_subscription ON licenses (stripe_subscription_id)
  WHERE stripe_subscription_id IS NOT NULL;

CREATE TABLE devices (
  id              TEXT PRIMARY KEY,
  license_id      TEXT NOT NULL REFERENCES licenses (id),
  machine_id      TEXT NOT NULL,
  device_name     TEXT,
  activated_at    INTEGER NOT NULL,
  last_verified_at INTEGER,
  deactivated_at  INTEGER,
  status          TEXT NOT NULL CHECK (status IN ('active', 'deactivated'))
);

-- One row per machine per license. Re-activating the same machine updates the
-- existing row rather than consuming a second seat.
CREATE UNIQUE INDEX idx_devices_license_machine ON devices (license_id, machine_id);
CREATE INDEX idx_devices_active ON devices (license_id, status);

CREATE TABLE verification_codes (
  id            TEXT PRIMARY KEY,
  license_id    TEXT NOT NULL REFERENCES licenses (id),
  email         TEXT NOT NULL,
  -- HMAC-SHA256 of the code under a server-side pepper. The plaintext code is
  -- never stored, and a six-digit code would be trivially brute-forced from a
  -- bare hash if the database ever leaked.
  code_hash     TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  expires_at    INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  used_at       INTEGER
);

CREATE INDEX idx_codes_email ON verification_codes (email, created_at);
CREATE INDEX idx_codes_license_open ON verification_codes (license_id, used_at);

-- Short-lived proof that an email was verified, exchanged for a device
-- activation. Keeps /verify-code from having to also perform activation.
CREATE TABLE activation_grants (
  id         TEXT PRIMARY KEY,
  license_id TEXT NOT NULL REFERENCES licenses (id),
  token_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at    INTEGER
);

CREATE INDEX idx_grants_open ON activation_grants (license_id, used_at);

-- Stripe redelivers events; this table is what makes the webhook idempotent.
CREATE TABLE stripe_events (
  id           TEXT PRIMARY KEY,
  type         TEXT NOT NULL,
  processed_at INTEGER NOT NULL
);

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
