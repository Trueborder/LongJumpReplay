-- Missing activation on an older plugin must never enable new bets.
ALTER TABLE bridge_status ADD COLUMN games_enabled INTEGER NOT NULL DEFAULT 0 CHECK(games_enabled IN (0,1));
