-- +goose Up
-- +goose StatementBegin
-- Phase 3: Shadow decision trace table (consolidated from in-Go CREATE TABLE in
-- cmd/lpbot/decision_trace.go). Required by the live schema guard in
-- cmd/lpbot/main.go (loadLiveSchemaState). The table records per-tick shadow
-- pipeline decisions (scanner -> audit -> strategy -> risk) and links to the
-- downstream positions/transactions when the decision graduates to on-chain.
--
-- Note: This migration is the source-of-truth for the schema. The in-Go
-- ensureShadowDecisionTraceTable helper is retained for backward compatibility
-- on already-deployed instances; new deployments should apply this migration
-- before the binary first starts.

CREATE TABLE IF NOT EXISTS shadow_decision_trace (
    id BIGSERIAL PRIMARY KEY,
    tick_time BIGINT NOT NULL,
    trace_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    pool_key TEXT NOT NULL,
    chain TEXT NOT NULL,
    protocol TEXT NOT NULL,
    score_total DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_json TEXT NOT NULL DEFAULT '',
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    selected_rank INTEGER,
    selection_reason TEXT NOT NULL DEFAULT '',
    intent_open BOOLEAN NOT NULL DEFAULT FALSE,
    intent_reason TEXT NOT NULL DEFAULT '',
    chain_stage TEXT NOT NULL DEFAULT '',
    chain_reason TEXT NOT NULL DEFAULT '',
    pipeline_stage TEXT NOT NULL DEFAULT '',
    pipeline_ok BOOLEAN NOT NULL DEFAULT FALSE,
    pipeline_reason TEXT NOT NULL DEFAULT '',
    final_action TEXT NOT NULL DEFAULT 'skip',
    position_id TEXT,
    tx_hash TEXT,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_created_at
    ON shadow_decision_trace(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_tick_time
    ON shadow_decision_trace(tick_time DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_pool_id
    ON shadow_decision_trace(pool_id);

-- Additive runtime columns (mirrored from the in-Go ensureShadowDecisionTraceTable
-- helper so existing rows from prior in-Go CREATE TABLE deployments still
-- satisfy the schema. New deployments get these on first apply.
ALTER TABLE shadow_decision_trace
    ADD COLUMN IF NOT EXISTS chain_stage TEXT NOT NULL DEFAULT '';
ALTER TABLE shadow_decision_trace
    ADD COLUMN IF NOT EXISTS chain_reason TEXT NOT NULL DEFAULT '';
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS shadow_decision_trace;
-- +goose StatementEnd
