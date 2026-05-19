-- +goose Up
-- +goose StatementBegin

-- Phase 0: Core LP position tracking tables

-- Primary pool registry with current state
CREATE TABLE dryrun_pools (
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

-- Pool score history for audit trail
CREATE TABLE dryrun_pool_score_history (
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

-- Active LP positions
CREATE TABLE dryrun_positions (
    position_id TEXT PRIMARY KEY,
    pool_id TEXT NOT NULL,
    chain INTEGER NOT NULL,
    status TEXT NOT NULL,
    token0_amount TEXT NOT NULL DEFAULT '0',
    token1_amount TEXT NOT NULL DEFAULT '0',
    tick_lower INTEGER,
    tick_upper INTEGER,
    liquidity TEXT,
    opened_at INTEGER NOT NULL,
    closed_at INTEGER,
    FOREIGN KEY (pool_id) REFERENCES dryrun_pools(pool_id)
);

CREATE INDEX idx_dryrun_positions_pool_id ON dryrun_positions(pool_id);
CREATE INDEX idx_dryrun_positions_chain ON dryrun_positions(chain);
CREATE INDEX idx_dryrun_positions_status ON dryrun_positions(status);
CREATE INDEX idx_dryrun_positions_opened_at ON dryrun_positions(opened_at);

-- Position status transition history
CREATE TABLE dryrun_position_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    block_ref TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    FOREIGN KEY (position_id) REFERENCES dryrun_positions(position_id)
);

CREATE INDEX idx_dryrun_position_history_position_id ON dryrun_position_history(position_id);
CREATE INDEX idx_dryrun_position_history_trace_id ON dryrun_position_history(trace_id);

-- Transaction log for monitoring state machine transactions
CREATE TABLE dryrun_tx_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain INTEGER NOT NULL,
    tx_hash TEXT NOT NULL UNIQUE,
    pool_id TEXT,
    status TEXT NOT NULL,
    rbf_attempts INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    broadcast_at INTEGER,
    mined_at INTEGER,
    confirmed_at INTEGER,
    FOREIGN KEY (pool_id) REFERENCES dryrun_pools(pool_id)
);

CREATE INDEX idx_dryrun_tx_log_chain ON dryrun_tx_log(chain);
CREATE INDEX idx_dryrun_tx_log_status ON dryrun_tx_log(status);
CREATE INDEX idx_dryrun_tx_log_created_at ON dryrun_tx_log(created_at);

-- Approval log for token spend tracking
CREATE TABLE dryrun_approve_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain INTEGER NOT NULL,
    token TEXT NOT NULL,
    spender TEXT NOT NULL,
    amount TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    block_ref TEXT NOT NULL
);

CREATE INDEX idx_dryrun_approve_log_chain ON dryrun_approve_log(chain);
CREATE INDEX idx_dryrun_approve_log_token ON dryrun_approve_log(token);
CREATE INDEX idx_dryrun_approve_log_tx_hash ON dryrun_approve_log(tx_hash);

-- PnL ledger for position performance tracking
CREATE TABLE dryrun_pnl_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain INTEGER NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT NOT NULL,
    block_time INTEGER NOT NULL,
    fee_usd TEXT NOT NULL DEFAULT '0',
    il_usd TEXT NOT NULL DEFAULT '0',
    swap_cost_usd TEXT NOT NULL DEFAULT '0',
    gas_usd TEXT NOT NULL DEFAULT '0',
    slippage_usd TEXT NOT NULL DEFAULT '0',
    rug_loss_usd TEXT NOT NULL DEFAULT '0',
    net_pnl_usd TEXT NOT NULL DEFAULT '0',
    trace_id TEXT NOT NULL,
    FOREIGN KEY (position_id) REFERENCES dryrun_positions(position_id),
    FOREIGN KEY (pool_id) REFERENCES dryrun_pools(pool_id)
);

CREATE INDEX idx_dryrun_pnl_ledger_position_id ON dryrun_pnl_ledger(position_id);
CREATE INDEX idx_dryrun_pnl_ledger_pool_id ON dryrun_pnl_ledger(pool_id);
CREATE INDEX idx_dryrun_pnl_ledger_chain ON dryrun_pnl_ledger(chain);
CREATE INDEX idx_dryrun_pnl_ledger_block_number ON dryrun_pnl_ledger(block_number);
CREATE INDEX idx_dryrun_pnl_ledger_trace_id ON dryrun_pnl_ledger(trace_id);

-- Processed events for idempotency checking
CREATE TABLE dryrun_processed_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    processed_at INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_processed_events_event_id ON dryrun_processed_events(event_id);

-- Config snapshots for reproducibility
CREATE TABLE dryrun_config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    env TEXT NOT NULL,
    hash TEXT NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL,
    timestamp INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_config_snapshots_env ON dryrun_config_snapshots(env);
CREATE INDEX idx_dryrun_config_snapshots_hash ON dryrun_config_snapshots(hash);
CREATE INDEX idx_dryrun_config_snapshots_timestamp ON dryrun_config_snapshots(timestamp);

-- Reconciliation log for health checks
CREATE TABLE dryrun_reconciliation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    env TEXT NOT NULL,
    chain INTEGER NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    message TEXT,
    timestamp INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_reconciliation_log_env ON dryrun_reconciliation_log(env);
CREATE INDEX idx_dryrun_reconciliation_log_chain ON dryrun_reconciliation_log(chain);
CREATE INDEX idx_dryrun_reconciliation_log_status ON dryrun_reconciliation_log(status);
CREATE INDEX idx_dryrun_reconciliation_log_timestamp ON dryrun_reconciliation_log(timestamp);

-- Risk events for monitoring and alerting
CREATE TABLE dryrun_risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT,
    pool_key TEXT,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    level TEXT NOT NULL,
    details TEXT,
    timestamp INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_risk_events_position_id ON dryrun_risk_events(position_id);
CREATE INDEX idx_dryrun_risk_events_pool_key ON dryrun_risk_events(pool_key);
CREATE INDEX idx_dryrun_risk_events_level ON dryrun_risk_events(level);
CREATE INDEX idx_dryrun_risk_events_timestamp ON dryrun_risk_events(timestamp);

-- Kill switch state for emergency controls
CREATE TABLE dryrun_kill_switch_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    sources_json TEXT,
    reason TEXT,
    unlocker TEXT,
    since INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_kill_switch_state_level ON dryrun_kill_switch_state(level);

-- Audit findings for pool risk assessment
CREATE TABLE dryrun_audit_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_key TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    timestamp INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_audit_findings_pool_key ON dryrun_audit_findings(pool_key);
CREATE INDEX idx_dryrun_audit_findings_severity ON dryrun_audit_findings(severity);
CREATE INDEX idx_dryrun_audit_findings_timestamp ON dryrun_audit_findings(timestamp);

-- Audit events for action tracking
CREATE TABLE dryrun_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_key TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    timestamp INTEGER NOT NULL
);

CREATE INDEX idx_dryrun_audit_events_pool_key ON dryrun_audit_events(pool_key);
CREATE INDEX idx_dryrun_audit_events_timestamp ON dryrun_audit_events(timestamp);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS dryrun_audit_events;
DROP TABLE IF EXISTS dryrun_audit_findings;
DROP TABLE IF EXISTS dryrun_kill_switch_state;
DROP TABLE IF EXISTS dryrun_risk_events;
DROP TABLE IF EXISTS dryrun_reconciliation_log;
DROP TABLE IF EXISTS dryrun_config_snapshots;
DROP TABLE IF EXISTS dryrun_processed_events;
DROP TABLE IF EXISTS dryrun_pnl_ledger;
DROP TABLE IF EXISTS dryrun_approve_log;
DROP TABLE IF EXISTS dryrun_tx_log;
DROP TABLE IF EXISTS dryrun_position_history;
DROP TABLE IF EXISTS dryrun_positions;
DROP TABLE IF EXISTS dryrun_pool_score_history;
DROP TABLE IF EXISTS dryrun_pools;

-- +goose StatementEnd