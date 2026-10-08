ALTER TABLE bridge_status ADD COLUMN games_version TEXT;
CREATE TABLE game_rounds (
 id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, uuid TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, game TEXT NOT NULL CHECK(game IN ('coin','dice','wheel')), currency TEXT NOT NULL CHECK(currency IN ('coins','tokens')),
 stake INTEGER NOT NULL CHECK(stake>=10 AND stake%10=0 AND stake<=9007199254740991), choice TEXT NOT NULL, rules_version TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','complete','rejected')), result TEXT, payout INTEGER, net INTEGER,
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, completed_at INTEGER,
 UNIQUE(customer_id,idempotency_key)
);
CREATE UNIQUE INDEX game_one_pending ON game_rounds(uuid) WHERE state='pending';
CREATE INDEX game_history ON game_rounds(customer_id,created_at);
CREATE TRIGGER game_cooldown BEFORE INSERT ON game_rounds
 WHEN EXISTS(SELECT 1 FROM game_rounds WHERE uuid=NEW.uuid AND created_at>NEW.created_at-5)
 BEGIN SELECT RAISE(ABORT,'game_cooldown'); END;
