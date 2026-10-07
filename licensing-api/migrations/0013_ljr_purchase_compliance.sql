-- LongJumpReplay-only purchase, policy and entitlement audit records.
-- EconomySuite uses a separate D1 database and is intentionally not referenced.
CREATE TABLE IF NOT EXISTS ljr_policy_versions (
  policy_key TEXT NOT NULL,
  version TEXT NOT NULL,
  effective_at INTEGER NOT NULL,
  PRIMARY KEY (policy_key, version)
);

CREATE TABLE IF NOT EXISTS ljr_orders (
  id TEXT PRIMARY KEY,
  customer_id TEXT REFERENCES customers(id),
  email TEXT NOT NULL,
  product_id TEXT NOT NULL DEFAULT 'LongJumpReplay',
  stripe_product_id TEXT,
  stripe_price_id TEXT NOT NULL,
  product_name TEXT NOT NULL,
  license_type TEXT NOT NULL CHECK (license_type IN ('lifetime','subscription')),
  displayed_price_minor INTEGER NOT NULL,
  currency TEXT NOT NULL,
  tax_notice TEXT NOT NULL,
  purchase_terms_version TEXT NOT NULL,
  eula_version TEXT NOT NULL,
  refund_policy_version TEXT NOT NULL,
  privacy_policy_version TEXT NOT NULL,
  consent_version TEXT NOT NULL,
  terms_accepted_at INTEGER NOT NULL,
  immediate_delivery_requested_at INTEGER NOT NULL,
  withdrawal_acknowledged_at INTEGER NOT NULL,
  consent_ip TEXT,
  consent_user_agent TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  stripe_checkout_session_id TEXT UNIQUE,
  stripe_customer_id TEXT,
  payment_intent_id TEXT,
  stripe_subscription_id TEXT,
  license_id TEXT,
  status TEXT NOT NULL DEFAULT 'checkout_pending' CHECK (status IN ('checkout_pending','paid','payment_failed','cancelled','refunded','partially_refunded','disputed','dispute_won','dispute_lost')),
  delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (delivery_status IN ('pending','delivered','failed','retrying','manual_review')),
  confirmation_status TEXT NOT NULL DEFAULT 'pending' CHECK (confirmation_status IN ('pending','sent','failed')),
  receipt_reference TEXT,
  refund_status TEXT,
  dispute_status TEXT,
  entitlement_status TEXT NOT NULL DEFAULT 'pending' CHECK (entitlement_status IN ('pending','active','suspended','revoked','manual_review')),
  paid_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ljr_orders_customer ON ljr_orders(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ljr_orders_email ON ljr_orders(email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ljr_orders_payment ON ljr_orders(payment_intent_id);
CREATE INDEX IF NOT EXISTS idx_ljr_orders_subscription ON ljr_orders(stripe_subscription_id);

CREATE TABLE IF NOT EXISTS ljr_order_events (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES ljr_orders(id),
  event_type TEXT NOT NULL,
  stripe_event_id TEXT,
  detail TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ljr_order_events_order ON ljr_order_events(order_id, created_at DESC);

INSERT OR IGNORE INTO ljr_policy_versions(policy_key, version, effective_at) VALUES
  ('purchase', '2026-10-07', 1791321600),
  ('eula', '2026-10-07', 1791321600),
  ('refund', '2026-10-07', 1791321600),
  ('privacy', '2026-10-07', 1791321600),
  ('consent', '2026-10-07', 1791321600),
  ('activation', '2026-10-07', 1791321600),
  ('updates', '2026-10-07', 1791321600);
