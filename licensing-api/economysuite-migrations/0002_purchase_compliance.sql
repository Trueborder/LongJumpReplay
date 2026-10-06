-- Purchase evidence and durable confirmations for digital EconomySuite orders.
-- IP data is stored only as a server-side hash; raw addresses are not retained.
ALTER TABLE store_orders ADD COLUMN checkout_key TEXT;
ALTER TABLE store_orders ADD COLUMN product_name TEXT;
ALTER TABLE store_orders ADD COLUMN displayed_currency TEXT;
ALTER TABLE store_orders ADD COLUMN displayed_price_minor INTEGER;
ALTER TABLE store_orders ADD COLUMN vat_notice TEXT;
ALTER TABLE store_orders ADD COLUMN policy_version TEXT;
ALTER TABLE store_orders ADD COLUMN immediate_delivery_requested INTEGER NOT NULL DEFAULT 0 CHECK(immediate_delivery_requested IN (0,1));
ALTER TABLE store_orders ADD COLUMN withdrawal_rights_acknowledged INTEGER NOT NULL DEFAULT 0 CHECK(withdrawal_rights_acknowledged IN (0,1));
ALTER TABLE store_orders ADD COLUMN consent_at INTEGER;
ALTER TABLE store_orders ADD COLUMN consent_ip_hash TEXT;
ALTER TABLE store_orders ADD COLUMN consent_user_agent TEXT;
ALTER TABLE store_orders ADD COLUMN receipt_reference TEXT;
ALTER TABLE store_orders ADD COLUMN order_confirmation_sent_at INTEGER;
CREATE UNIQUE INDEX store_orders_checkout_key ON store_orders(checkout_key) WHERE checkout_key IS NOT NULL;

CREATE TABLE purchase_consents (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL UNIQUE REFERENCES store_orders(id),
  customer_id TEXT NOT NULL,
  accepted_at INTEGER NOT NULL,
  policy_version TEXT NOT NULL,
  terms_version TEXT NOT NULL,
  refund_version TEXT NOT NULL,
  delivery_version TEXT NOT NULL,
  immediate_delivery_requested INTEGER NOT NULL CHECK(immediate_delivery_requested IN (0,1)),
  withdrawal_rights_acknowledged INTEGER NOT NULL CHECK(withdrawal_rights_acknowledged IN (0,1)),
  ip_hash TEXT,
  user_agent TEXT,
  product_id TEXT NOT NULL,
  product_name TEXT NOT NULL,
  displayed_price_minor INTEGER NOT NULL,
  displayed_currency TEXT NOT NULL,
  vat_notice TEXT NOT NULL
);
CREATE INDEX purchase_consents_customer ON purchase_consents(customer_id,accepted_at);

CREATE TABLE order_confirmations (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL UNIQUE REFERENCES store_orders(id),
  customer_id TEXT NOT NULL,
  email TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','sent','failed')),
  provider_reference TEXT,
  error_code TEXT,
  created_at INTEGER NOT NULL,
  sent_at INTEGER
);
CREATE INDEX order_confirmations_customer ON order_confirmations(customer_id,created_at);
