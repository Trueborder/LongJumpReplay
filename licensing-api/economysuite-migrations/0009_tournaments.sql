-- Separate from financial operations: web administrators need not have a player UUID.
CREATE TABLE tournament_snapshots(id TEXT PRIMARY KEY,payload TEXT NOT NULL,revision INTEGER NOT NULL,synced_at INTEGER NOT NULL);
CREATE TABLE tournament_operations(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,player_uuid TEXT,action TEXT NOT NULL,payload TEXT NOT NULL,tournament_id TEXT NOT NULL,revision INTEGER NOT NULL,instance TEXT NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'pending',result TEXT,completed_at INTEGER);
CREATE INDEX tournament_operations_pending ON tournament_operations(state,created_at);
CREATE TABLE tournament_admins(customer_id TEXT PRIMARY KEY,created_at INTEGER NOT NULL,owner_key TEXT NOT NULL UNIQUE DEFAULT 'owner');
CREATE TABLE tournament_reauth(token_hash TEXT PRIMARY KEY,customer_id TEXT NOT NULL,session_hash TEXT NOT NULL,expires_at INTEGER NOT NULL);
