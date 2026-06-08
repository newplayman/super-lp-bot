-- +goose Up
-- +goose StatementBegin
-- Phase 3: Shadow exit decisions and exit actions tables (consolidated from
-- in-Go CREATE TABLE in cmd/lpbot/position_mark.go:147-180 and 185-220).
-- Records shadow exit pipeline decisions and the resulting action (or hold).
-- Source-of-truth for the schema; in-Go ensure*Table helpers retained for
-- backward compat on already-deployed instances.

CREATE TABLE IF NOT EXISTS shadow_exit_decisions (
    id BIGSERIAL PRIMARY KEY,
    decision_time BIGINT NOT NULL,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    status TEXT NOT NULL,
    tier TEXT NOT NULL,
    amount_usd TEXT NOT NULL DEFAULT '0',
    hold_minutes BIGINT NOT NULL DEFAULT 0,
    current_tvl_usd TEXT NOT NULL DEFAULT '0',
    net_pnl_usd TEXT NOT NULL DEFAULT '0',
    il_usd TEXT NOT NULL DEFAULT '0',
    price_change_pct TEXT NOT NULL DEFAULT '0',
    would_exit BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT 'hold',
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_exit_decisions_position_time
    ON shadow_exit_decisions(position_id, decision_time DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_exit_decisions_decision_time
    ON shadow_exit_decisions(decision_time DESC);

CREATE TABLE IF NOT EXISTS shadow_exit_actions (
    id BIGSERIAL PRIMARY KEY,
    decision_time BIGINT NOT NULL,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    tx_hash TEXT NOT NULL DEFAULT '',
    tx_status TEXT NOT NULL DEFAULT '',
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_exit_actions_position_time
    ON shadow_exit_actions(position_id, decision_time DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_exit_actions_decision_time
    ON shadow_exit_actions(decision_time DESC);
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS shadow_exit_actions;
DROP TABLE IF EXISTS shadow_exit_decisions;
-- +goose StatementEnd
