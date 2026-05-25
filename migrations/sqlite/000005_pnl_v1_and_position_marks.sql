-- +goose Up
-- +goose StatementBegin

ALTER TABLE pnl_ledger ADD COLUMN kind TEXT NOT NULL DEFAULT '';
ALTER TABLE pnl_ledger ADD COLUMN amount TEXT NOT NULL DEFAULT '0';
ALTER TABLE pnl_ledger ADD COLUMN token_symbol TEXT NOT NULL DEFAULT 'USD';
ALTER TABLE pnl_ledger ADD COLUMN source TEXT NOT NULL DEFAULT '';
ALTER TABLE pnl_ledger ADD COLUMN position_value_usd TEXT NOT NULL DEFAULT '0';
ALTER TABLE pnl_ledger ADD COLUMN fee_collected_usd TEXT NOT NULL DEFAULT '0';
ALTER TABLE pnl_ledger ADD COLUMN fee_uncollected_usd TEXT NOT NULL DEFAULT '0';
ALTER TABLE pnl_ledger ADD COLUMN lvr_usd TEXT NOT NULL DEFAULT '0';

ALTER TABLE portfolio_snapshots ADD COLUMN stuck_tx_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE portfolio_snapshots ADD COLUMN exit_failed_position_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE portfolio_snapshots ADD COLUMN unreconciled_opening_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE portfolio_snapshots ADD COLUMN unreconciled_opening_timeout_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS position_marks (
    id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    token_id TEXT,
    status TEXT NOT NULL,
    amount_usd TEXT NOT NULL DEFAULT '0',
    position_value_usd TEXT NOT NULL DEFAULT '0',
    fee_collected_usd TEXT NOT NULL DEFAULT '0',
    fee_uncollected_usd TEXT NOT NULL DEFAULT '0',
    gas_usd TEXT NOT NULL DEFAULT '0',
    il_usd TEXT NOT NULL DEFAULT '0',
    lvr_usd TEXT NOT NULL DEFAULT '0',
    net_pnl_usd TEXT NOT NULL DEFAULT '0',
    source TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    mark_time INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_position_marks_position_time
    ON position_marks(position_id, mark_time DESC);
CREATE INDEX IF NOT EXISTS idx_position_marks_chain_status
    ON position_marks(chain, status, mark_time DESC);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS position_marks;

-- SQLite down migration keeps additive columns in place.

-- +goose StatementEnd
