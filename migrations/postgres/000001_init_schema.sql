-- PostgreSQL schema initialization for lp-bot shadow/live stores.
-- Generated for current adapter expectations.

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    chain TEXT NOT NULL,
    tx_hash TEXT NOT NULL UNIQUE,
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    data BYTEA,
    value TEXT NOT NULL DEFAULT '0',
    nonce BIGINT NOT NULL DEFAULT 0,
    deadline BIGINT NOT NULL DEFAULT 0,
    min_out TEXT NOT NULL DEFAULT '0',
    signature BYTEA,
    status TEXT NOT NULL DEFAULT 'built',
    block_number BIGINT,
    block_hash TEXT,
    broadcast_at BIGINT,
    gas_used TEXT,
    gas_price TEXT,
    gas_limit TEXT,
    rfb_attempts INTEGER NOT NULL DEFAULT 0,
    error_msg TEXT,
    trace_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_chain_status ON transactions(chain, status);
CREATE INDEX IF NOT EXISTS idx_transactions_hash ON transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_transactions_broadcast_at ON transactions(broadcast_at);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    pool_id TEXT NOT NULL,
    chain INTEGER NOT NULL,
    status TEXT NOT NULL,
    tier TEXT,
    tick_lower BIGINT NOT NULL,
    tick_upper BIGINT NOT NULL,
    amount_usd TEXT NOT NULL DEFAULT '0',
    opened_at BIGINT NOT NULL,
    closed_at BIGINT
);

CREATE TABLE IF NOT EXISTS pools (
    pool_id TEXT NOT NULL,
    chain INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    token0 TEXT NOT NULL,
    token1 TEXT NOT NULL,
    fee_bps INTEGER NOT NULL,
    tier TEXT,
    audit_verdict TEXT,
    last_score TEXT,
    updated_block BIGINT DEFAULT 0,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (pool_id, chain, protocol)
);

CREATE TABLE IF NOT EXISTS pool_score_history (
    id BIGSERIAL PRIMARY KEY,
    pool_id TEXT NOT NULL,
    chain INTEGER NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash TEXT,
    block_time BIGINT NOT NULL,
    score_json TEXT NOT NULL,
    trace_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_pool_score_history_pool_id ON pool_score_history(pool_id);
CREATE INDEX IF NOT EXISTS idx_pool_score_history_block ON pool_score_history(pool_id, block_number);

CREATE TABLE IF NOT EXISTS pnl_ledger (
    id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount TEXT NOT NULL DEFAULT '0',
    token_symbol TEXT NOT NULL,
    chain INTEGER NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash TEXT,
    block_time BIGINT NOT NULL,
    tx_hash TEXT
);

CREATE TABLE IF NOT EXISTS risk_events (
    id TEXT PRIMARY KEY,
    position_id TEXT,
    pool_key TEXT,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    level TEXT NOT NULL,
    details TEXT,
    timestamp BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS kill_switch_state (
    id BIGSERIAL PRIMARY KEY,
    level TEXT NOT NULL,
    sources TEXT,
    since BIGINT NOT NULL,
    reason TEXT,
    unlocker TEXT
);

CREATE TABLE IF NOT EXISTS config_snapshots (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    block_number BIGINT,
    trace_id TEXT,
    created_at BIGINT NOT NULL
);
