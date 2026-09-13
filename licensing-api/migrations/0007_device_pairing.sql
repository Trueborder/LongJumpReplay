CREATE TABLE IF NOT EXISTS device_pairing_sessions (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  code_hash TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  device_name TEXT,
  app_version TEXT,
  os_version TEXT,
  architecture TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'used', 'expired')),
  customer_id TEXT REFERENCES customers(id),
  license_id TEXT REFERENCES licenses(id),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  approved_at INTEGER,
  used_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_device_pairing_code ON device_pairing_sessions(code_hash, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_device_pairing_expiry ON device_pairing_sessions(expires_at, status);
