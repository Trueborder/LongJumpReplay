-- Keep QR approval outcomes visible long enough for both the browser and the
-- desktop client to explain what happened. SQLite requires a table rebuild to
-- extend the status CHECK constraint.
PRAGMA foreign_keys = OFF;

CREATE TABLE device_pairing_sessions_v2 (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  code_hash TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  device_name TEXT,
  app_version TEXT,
  os_version TEXT,
  architecture TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'activating', 'used', 'declined', 'failed', 'expired')),
  customer_id TEXT REFERENCES customers(id),
  license_id TEXT REFERENCES licenses(id),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  approved_at INTEGER,
  used_at INTEGER,
  result_code TEXT,
  result_message TEXT,
  completed_at INTEGER,
  activation_started_at INTEGER
);

INSERT INTO device_pairing_sessions_v2
  (id, token_hash, code_hash, machine_id, device_name, app_version, os_version,
   architecture, status, customer_id, license_id, created_at, expires_at,
   approved_at, used_at, result_code, completed_at)
SELECT id, token_hash, code_hash, machine_id, device_name, app_version, os_version,
   architecture, status, customer_id, license_id, created_at, expires_at,
   approved_at, used_at,
   CASE WHEN status = 'used' THEN 'activated' ELSE NULL END,
   CASE WHEN status = 'used' THEN used_at ELSE NULL END
FROM device_pairing_sessions;

DROP TABLE device_pairing_sessions;
ALTER TABLE device_pairing_sessions_v2 RENAME TO device_pairing_sessions;

CREATE INDEX IF NOT EXISTS idx_device_pairing_code ON device_pairing_sessions(code_hash, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_device_pairing_expiry ON device_pairing_sessions(expires_at, status);

PRAGMA foreign_keys = ON;
