-- +goose Up
-- +goose StatementBegin

-- Base tables (prefix applied at runtime via applySchemaPrefix)
CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    token_id TEXT,
    chain TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    protocol TEXT,
    token0 TEXT NOT NULL,
    token1 TEXT NOT NULL,
    tick_lower INTEGER NOT NULL,
    tick_upper INTEGER NOT NULL,
    liquidity TEXT NOT NULL,
    amount0 TEXT NOT NULL,
    amount1 TEXT NOT NULL,
    tvl_usd TEXT,
    amount_usd TEXT,
    tier TEXT,
    open_tx_hash TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    fee_growth_0 TEXT,
    fee_growth_1 TEXT,
    collected_fee_0 TEXT,
    collected_fee_1 TEXT,
    opened_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    closed_at INTEGER,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    order_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    executed_at INTEGER,
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    chain TEXT NOT NULL,
    tx_hash TEXT NOT NULL UNIQUE,
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    data BLOB,
    value TEXT NOT NULL DEFAULT '0',
    nonce INTEGER NOT NULL DEFAULT 0,
    deadline INTEGER NOT NULL DEFAULT 0,
    min_out TEXT NOT NULL DEFAULT '0',
    signature BLOB,
    status TEXT NOT NULL DEFAULT 'built',
    block_number INTEGER,
    block_hash TEXT,
    broadcast_at INTEGER,
    gas_used INTEGER,
    gas_price TEXT,
    gas_limit INTEGER,
    rfb_attempts INTEGER NOT NULL DEFAULT 0,
    error_msg TEXT,
    trace_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_chain_status ON transactions(chain, status);
CREATE INDEX IF NOT EXISTS idx_transactions_hash ON transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_transactions_broadcast_at ON transactions(broadcast_at);

CREATE TABLE IF NOT EXISTS pool_states (
    id TEXT PRIMARY KEY,
    pool_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    liquidity TEXT NOT NULL,
    observation_cardinality INTEGER,
    snapshot_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pools (
    id TEXT PRIMARY KEY,
    chain TEXT NOT NULL,
    protocol TEXT NOT NULL,
    token0 TEXT NOT NULL,
    token1 TEXT NOT NULL,
    fee_bps INTEGER NOT NULL,
    tier TEXT NOT NULL,
    tvl_usd TEXT,
    vol_24h TEXT,
    fee_apr_24h TEXT,
    last_score REAL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT,
    block_time INTEGER NOT NULL,
    score_json TEXT NOT NULL,
    trace_id TEXT
);

CREATE TABLE IF NOT EXISTS pnl_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT,
    block_time INTEGER NOT NULL,
    fee_usd TEXT NOT NULL DEFAULT '0',
    il_usd TEXT NOT NULL DEFAULT '0',
    swap_cost_usd TEXT NOT NULL DEFAULT '0',
    gas_usd TEXT NOT NULL DEFAULT '0',
    slippage_usd TEXT NOT NULL DEFAULT '0',
    rug_loss_usd TEXT NOT NULL DEFAULT '0',
    net_pnl_usd TEXT NOT NULL DEFAULT '0',
    trace_id TEXT
);

CREATE TABLE IF NOT EXISTS processed_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_topic TEXT NOT NULL,
    processed_at INTEGER NOT NULL,
    expires_at INTEGER
);

CREATE TABLE IF NOT EXISTS config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    block_number INTEGER,
    trace_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    expected_usd TEXT NOT NULL,
    actual_usd TEXT NOT NULL,
    variance_usd TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    trace_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_events (
    id TEXT PRIMARY KEY,
    position_id TEXT,
    pool_key TEXT,
    event_type TEXT NOT NULL,
    action TEXT,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    data TEXT,
    resolved INTEGER DEFAULT 0,
    resolved_at INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
    id TEXT PRIMARY KEY,
    position_id TEXT,
    tx_hash TEXT,
    entry_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    description TEXT,
    timestamp INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kill_switch_state (
    id TEXT PRIMARY KEY,
    switch_type TEXT NOT NULL,
    triggered_at INTEGER NOT NULL,
    trigger_reason TEXT,
    auto_resume_at INTEGER,
    resumed_at INTEGER,
    resume_allowed INTEGER DEFAULT 1,
    total_triggers INTEGER DEFAULT 1,
    updated_at INTEGER NOT NULL
);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS kill_switch_state;
DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS risk_events;
DROP TABLE IF EXISTS reconciliation_log;
DROP TABLE IF EXISTS config_snapshots;
DROP TABLE IF EXISTS processed_events;
DROP TABLE IF EXISTS pnl_ledger;
DROP TABLE IF EXISTS pool_score_history;
DROP TABLE IF EXISTS pools;
DROP TABLE IF EXISTS pool_states;
DROP INDEX IF EXISTS idx_transactions_chain_status;
DROP INDEX IF EXISTS idx_transactions_hash;
DROP INDEX IF EXISTS idx_transactions_broadcast_at;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS positions;

-- +goose StatementEnd
