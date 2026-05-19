-- Clean schema for sqlc: pools table only (no goose annotations)
CREATE TABLE IF NOT EXISTS dryrun_pools (
    pool_id TEXT PRIMARY KEY,
    chain INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    token0 TEXT NOT NULL,
    token1 TEXT NOT NULL,
    fee_bps INTEGER NOT NULL,
    tier TEXT,
    audit_verdict TEXT,
    last_score TEXT,
    updated_block INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_pools_chain ON dryrun_pools(chain);
CREATE INDEX idx_dryrun_pools_protocol ON dryrun_pools(protocol);
CREATE INDEX idx_dryrun_pools_updated_block ON dryrun_pools(updated_block);

CREATE TABLE IF NOT EXISTS dryrun_pool_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id TEXT NOT NULL,
    chain INTEGER NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT NOT NULL,
    block_time INTEGER NOT NULL,
    score_json TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    FOREIGN KEY (pool_id) REFERENCES dryrun_pools(pool_id)
);

CREATE INDEX idx_dryrun_pool_score_history_pool_id ON dryrun_pool_score_history(pool_id);
CREATE INDEX idx_dryrun_pool_score_history_block_number ON dryrun_pool_score_history(block_number);
CREATE INDEX idx_dryrun_pool_score_history_trace_id ON dryrun_pool_score_history(trace_id);