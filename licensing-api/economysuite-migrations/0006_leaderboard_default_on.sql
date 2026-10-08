-- Apply the requested default to current links and future pairing.
-- SQLite requires recreating this table to change its column default.
CREATE TABLE player_links_default_on (
  customer_id TEXT PRIMARY KEY,
  uuid TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  linked_at INTEGER NOT NULL,
  leaderboard INTEGER NOT NULL DEFAULT 1 CHECK(leaderboard IN (0,1))
);
INSERT INTO player_links_default_on(customer_id,uuid,name,linked_at,leaderboard)
SELECT l.customer_id,l.uuid,l.name,l.linked_at,
  CASE WHEN EXISTS(SELECT 1 FROM customers c WHERE c.id=l.customer_id AND lower(c.email)='xpisar10@gmail.com')
       THEN l.leaderboard ELSE 1 END
FROM player_links l;
DROP TABLE player_links;
ALTER TABLE player_links_default_on RENAME TO player_links;
