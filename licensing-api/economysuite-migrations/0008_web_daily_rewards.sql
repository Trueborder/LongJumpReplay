CREATE TABLE web_daily_rewards (
  uuid TEXT NOT NULL,
  day TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  tokens INTEGER NOT NULL CHECK(tokens BETWEEN 1 AND 5),
  operation_id TEXT NOT NULL UNIQUE,
  claimed_at INTEGER NOT NULL,
  PRIMARY KEY(uuid, day)
);
CREATE INDEX web_daily_customer ON web_daily_rewards(customer_id,day);
ALTER TABLE bridge_status ADD COLUMN web_daily_version INTEGER NOT NULL DEFAULT 0;
