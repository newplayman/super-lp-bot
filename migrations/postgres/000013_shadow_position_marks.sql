-- +goose Up
-- +goose StatementBegin
-- Phase 3: Shadow position marks table (consolidated from in-Go CREATE TABLE in
-- cmd/lpbot/position_mark.go:103-135). Records per-position periodic marks
-- (mark_time, current_tvl_usd, current_vol24h_usd, price_change_pct, etc.) for
-- shadow P&L tracking. Source-of-truth for the schema; the in-Go
-- ensureShadowPositionMarksTable helper is retained for backward compat on
-- already-deployed instances.

CREATE TABLE IF NOT EXISTS shadow_position_marks (
    id BIGSERIAL PRIMARY KEY,
    mark_time BIGINT NOT NULL,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    status TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT '',
    amount_usd TEXT NOT NULL DEFAULT '0',
    source TEXT NOT NULL DEFAULT '',
    hold_minutes BIGINT NOT NULL DEFAULT 0,
    valuation_usd TEXT NOT NULL DEFAULT '0',
    fee_usd TEXT NOT NULL DEFAULT '0',
    il_usd TEXT NOT NULL DEFAULT '0',
    net_pnl_usd TEXT NOT NULL DEFAULT '0',
    current_tvl_usd TEXT NOT NULL DEFAULT '0',
    current_vol24h_usd TEXT NOT NULL DEFAULT '0',
    price_change_pct TEXT NOT NULL DEFAULT '0',
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_position_marks_position_time
    ON shadow_position_marks(position_id, mark_time DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_position_marks_mark_time
    ON shadow_position_marks(mark_time DESC);
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS shadow_position_marks;
-- +goose StatementEnd
