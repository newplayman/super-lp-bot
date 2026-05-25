-- +goose Up
-- +goose StatementBegin

CREATE TABLE IF NOT EXISTS shadow_outcome_labels (
    id TEXT PRIMARY KEY,
    decision_trace_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL DEFAULT '',
    decision_time INTEGER NOT NULL,
    score_total REAL NOT NULL DEFAULT 0,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    intent_open BOOLEAN NOT NULL DEFAULT FALSE,
    horizon TEXT NOT NULL,
    entry_value_usd TEXT NOT NULL DEFAULT '0',
    simulated_position_value_usd TEXT NOT NULL DEFAULT '0',
    simulated_fee_usd TEXT NOT NULL DEFAULT '0',
    simulated_gas_usd TEXT NOT NULL DEFAULT '0',
    simulated_il_usd TEXT NOT NULL DEFAULT '0',
    simulated_net_pnl_usd TEXT NOT NULL DEFAULT '0',
    max_drawdown_usd TEXT NOT NULL DEFAULT '0',
    label TEXT NOT NULL DEFAULT 'invalid',
    created_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_outcomes_trace_horizon
    ON shadow_outcome_labels(decision_trace_id, horizon);
CREATE INDEX IF NOT EXISTS idx_shadow_outcomes_horizon_created
    ON shadow_outcome_labels(horizon, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_outcomes_pool_horizon
    ON shadow_outcome_labels(pool_id, horizon, created_at DESC);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS shadow_outcome_labels;

-- +goose StatementEnd
