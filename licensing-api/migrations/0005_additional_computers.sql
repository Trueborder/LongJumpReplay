-- One-time lifetime seat purchases. A unique Stripe session makes webhook
-- retries and duplicate deliveries harmless.
CREATE TABLE additional_computer_purchases (
  stripe_session_id TEXT PRIMARY KEY,
  stripe_payment_intent_id TEXT,
  customer_id TEXT NOT NULL REFERENCES customers (id),
  license_id TEXT NOT NULL REFERENCES licenses (id),
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 8),
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL,
  resulting_max_devices INTEGER,
  processed_at INTEGER NOT NULL
);
CREATE INDEX idx_additional_purchases_license ON additional_computer_purchases (license_id, processed_at);
