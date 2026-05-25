-- +goose Up
-- +goose StatementBegin

ALTER TABLE pnl_ledger
    ADD COLUMN IF NOT EXISTS pool_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS position_value_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS fee_collected_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS fee_uncollected_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS gas_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS il_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS lvr_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS net_pnl_usd TEXT NOT NULL DEFAULT '0',
    ADD COLUMN IF NOT EXISTS trace_id TEXT;

ALTER TABLE portfolio_snapshots
    ADD COLUMN IF NOT EXISTS stuck_tx_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS exit_failed_position_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unreconciled_opening_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unreconciled_opening_timeout_count INTEGER NOT NULL DEFAULT 0;

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
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    mark_time BIGINT NOT NULL,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_position_marks_position_time
    ON position_marks(position_id, mark_time DESC);
CREATE INDEX IF NOT EXISTS idx_position_marks_chain_status
    ON position_marks(chain, status, mark_time DESC);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS position_marks;

ALTER TABLE portfolio_snapshots
    DROP COLUMN IF EXISTS unreconciled_opening_timeout_count,
    DROP COLUMN IF EXISTS unreconciled_opening_count,
    DROP COLUMN IF EXISTS exit_failed_position_count,
    DROP COLUMN IF EXISTS stuck_tx_count;

ALTER TABLE pnl_ledger
    DROP COLUMN IF EXISTS trace_id,
    DROP COLUMN IF EXISTS net_pnl_usd,
    DROP COLUMN IF EXISTS lvr_usd,
    DROP COLUMN IF EXISTS il_usd,
    DROP COLUMN IF EXISTS gas_usd,
    DROP COLUMN IF EXISTS fee_uncollected_usd,
    DROP COLUMN IF EXISTS fee_collected_usd,
    DROP COLUMN IF EXISTS position_value_usd,
    DROP COLUMN IF EXISTS source,
    DROP COLUMN IF EXISTS pool_id;

-- +goose StatementEnd
