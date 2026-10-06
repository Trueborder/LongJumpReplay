-- User-facing data export and deletion-request audit trail.
CREATE TABLE IF NOT EXISTS privacy_requests (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  type TEXT NOT NULL CHECK(type IN ('export','deletion')),
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','completed','rejected')),
  created_at INTEGER NOT NULL,
  completed_at INTEGER,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_privacy_requests_customer ON privacy_requests(customer_id,created_at);
