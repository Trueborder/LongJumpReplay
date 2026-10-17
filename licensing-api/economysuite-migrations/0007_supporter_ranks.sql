-- Preserve existing payment evidence and foreign-key references while extending product kinds.
-- Apply as one migration transaction; never disable foreign-key enforcement.
PRAGMA defer_foreign_keys = ON;
CREATE TABLE store_orders_rank_upgrade (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, uuid TEXT NOT NULL, player_name TEXT NOT NULL,
  price_id TEXT NOT NULL, currency_type TEXT NOT NULL CHECK(currency_type IN ('coins','tokens','rank')),
  currency_amount INTEGER NOT NULL, price_minor INTEGER NOT NULL, session_id TEXT UNIQUE,
  payment_intent TEXT UNIQUE, dispute_id TEXT, paid INTEGER NOT NULL DEFAULT 0,
  target_amount INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
  delivered_revision INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'checkout', receipt_url TEXT,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  checkout_key TEXT, product_name TEXT, displayed_currency TEXT, displayed_price_minor INTEGER,
  vat_notice TEXT, policy_version TEXT,
  immediate_delivery_requested INTEGER NOT NULL DEFAULT 0 CHECK(immediate_delivery_requested IN (0,1)),
  withdrawal_rights_acknowledged INTEGER NOT NULL DEFAULT 0 CHECK(withdrawal_rights_acknowledged IN (0,1)),
  consent_at INTEGER, consent_ip_hash TEXT, consent_user_agent TEXT, receipt_reference TEXT,
  order_confirmation_sent_at INTEGER,
  product_type TEXT NOT NULL DEFAULT 'currency' CHECK(product_type IN ('currency','rank')),
  rank_id TEXT CHECK(rank_id IN ('vip','vipplus','mvp')), rank_paid_at INTEGER,
  CHECK((product_type='currency' AND currency_type IN ('coins','tokens') AND rank_id IS NULL) OR
        (product_type='rank' AND currency_type='rank' AND rank_id IS NOT NULL AND currency_amount=604800))
);
INSERT INTO store_orders_rank_upgrade (
  id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,session_id,payment_intent,
  dispute_id,paid,target_amount,revision,delivered_revision,state,receipt_url,created_at,updated_at,checkout_key,
  product_name,displayed_currency,displayed_price_minor,vat_notice,policy_version,immediate_delivery_requested,
  withdrawal_rights_acknowledged,consent_at,consent_ip_hash,consent_user_agent,receipt_reference,order_confirmation_sent_at
) SELECT id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,session_id,payment_intent,
  dispute_id,paid,target_amount,revision,delivered_revision,state,receipt_url,created_at,updated_at,checkout_key,
  product_name,displayed_currency,displayed_price_minor,vat_notice,policy_version,immediate_delivery_requested,
  withdrawal_rights_acknowledged,consent_at,consent_ip_hash,consent_user_agent,receipt_reference,order_confirmation_sent_at
FROM store_orders;
DROP TABLE store_orders;
ALTER TABLE store_orders_rank_upgrade RENAME TO store_orders;
CREATE INDEX orders_customer ON store_orders(customer_id,created_at);
CREATE UNIQUE INDEX store_orders_checkout_key ON store_orders(checkout_key) WHERE checkout_key IS NOT NULL;
PRAGMA foreign_key_check;
PRAGMA defer_foreign_keys = OFF;
ALTER TABLE bridge_status ADD COLUMN ranks_version INTEGER NOT NULL DEFAULT 0;
