CREATE TABLE public_server_snapshot (id TEXT PRIMARY KEY CHECK(id='pantheon'), payload TEXT NOT NULL, synced_at INTEGER NOT NULL);
