ALTER TABLE devices ADD COLUMN activation_method TEXT NOT NULL DEFAULT 'email'
  CHECK (activation_method IN ('email', 'key'));
ALTER TABLE devices ADD COLUMN activation_key_generation INTEGER;
ALTER TABLE devices ADD COLUMN app_version TEXT;
ALTER TABLE devices ADD COLUMN os_version TEXT;
ALTER TABLE devices ADD COLUMN architecture TEXT;

CREATE TABLE license_activation_keys (
  license_id TEXT PRIMARY KEY REFERENCES licenses(id) ON DELETE CASCADE,
  generation INTEGER NOT NULL DEFAULT 1,
  verifier_hash TEXT NOT NULL UNIQUE,
  ciphertext TEXT NOT NULL,
  nonce TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  rotated_at INTEGER
);

CREATE TABLE device_activity (
  id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  license_id TEXT NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN ('activation', 'verification')),
  ip_address TEXT,
  country TEXT,
  app_version TEXT,
  os_version TEXT,
  architecture TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_device_activity_device_time ON device_activity(device_id, created_at DESC);
CREATE INDEX idx_device_activity_created ON device_activity(created_at);
CREATE INDEX idx_devices_activation_method ON devices(license_id, activation_method, activation_key_generation);
