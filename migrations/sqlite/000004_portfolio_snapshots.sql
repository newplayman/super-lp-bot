-- +goose Up
-- +goose StatementBegin
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    chain TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    native_balance_wei TEXT NOT NULL DEFAULT '0',
    gas_reserve_wei TEXT NOT NULL DEFAULT '0',
    open_position_count INTEGER NOT NULL DEFAULT 0,
    open_position_exposure_usd TEXT NOT NULL DEFAULT '0',
    pending_exposure_usd TEXT NOT NULL DEFAULT '0',
    submitted_private_exposure_usd TEXT NOT NULL DEFAULT '0',
    realized_pnl_usd TEXT NOT NULL DEFAULT '0',
    unrealized_pnl_usd TEXT NOT NULL DEFAULT '0',
    balances_json TEXT NOT NULL DEFAULT '{}',
    positions_json TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_chain_created_at
    ON portfolio_snapshots(chain, created_at DESC);
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS portfolio_snapshots;
-- +goose StatementEnd
