-- +goose Up
-- +goose StatementBegin

CREATE TABLE IF NOT EXISTS shadow_outcome_labels_repaired_v2 (
    id TEXT PRIMARY KEY,
    decision_trace_id TEXT NOT NULL,
    horizon TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    position_id TEXT NOT NULL DEFAULT '',
    score_total REAL NOT NULL DEFAULT 0,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    intent_open BOOLEAN NOT NULL DEFAULT FALSE,
    label TEXT NOT NULL DEFAULT 'invalid',
    entry_value_usd_repaired TEXT NOT NULL DEFAULT '0',
    entry_value_source TEXT NOT NULL DEFAULT '',
    entry_value_confidence TEXT NOT NULL DEFAULT '',
    metadata_source TEXT NOT NULL DEFAULT '',
    decimals_source TEXT NOT NULL DEFAULT '',
    price_source TEXT NOT NULL DEFAULT '',
    position_id_source TEXT NOT NULL DEFAULT '',
    position_id_confidence TEXT NOT NULL DEFAULT '',
    mark_source TEXT NOT NULL DEFAULT '',
    repair_version TEXT NOT NULL DEFAULT 'v2',
    valid_entry_strict BOOLEAN NOT NULL DEFAULT FALSE,
    invalid_reason_repaired TEXT NOT NULL DEFAULT '',
    net_pnl_usd_repaired TEXT NOT NULL DEFAULT '0',
    net_pnl_pct_repaired TEXT NOT NULL DEFAULT '0',
    created_at INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_repaired_v2_trace_horizon_version
    ON shadow_outcome_labels_repaired_v2(decision_trace_id, horizon, repair_version);
CREATE INDEX IF NOT EXISTS idx_shadow_repaired_v2_horizon_created
    ON shadow_outcome_labels_repaired_v2(horizon, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_repaired_v2_pool_horizon
    ON shadow_outcome_labels_repaired_v2(pool_id, horizon, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_repaired_v2_invalid_reason
    ON shadow_outcome_labels_repaired_v2(invalid_reason_repaired, horizon);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS shadow_outcome_labels_repaired_v2;

-- +goose StatementEnd
