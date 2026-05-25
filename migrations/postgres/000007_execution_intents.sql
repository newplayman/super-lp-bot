-- +goose Up
-- +goose StatementBegin
CREATE TABLE IF NOT EXISTS execution_intents (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    chain TEXT NOT NULL,
    pool_id TEXT,
    position_id TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    unsigned_tx_hash TEXT,
    signed_tx_hash TEXT,
    tx_hash TEXT,
    reason TEXT,
    risk_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sizing_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision_trace_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_intents_chain_status
    ON execution_intents(chain, status);
CREATE INDEX IF NOT EXISTS idx_execution_intents_tx_hash
    ON execution_intents(chain, tx_hash);
CREATE INDEX IF NOT EXISTS idx_execution_intents_position
    ON execution_intents(position_id, action, status);
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS execution_intents;
-- +goose StatementEnd
