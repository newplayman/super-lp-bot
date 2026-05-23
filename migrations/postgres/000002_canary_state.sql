CREATE TABLE IF NOT EXISTS canary_events (
    id TEXT PRIMARY KEY,
    chain TEXT NOT NULL DEFAULT '',
    command TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    position_id TEXT NOT NULL DEFAULT '',
    pool_id TEXT NOT NULL DEFAULT '',
    wallet TEXT NOT NULL DEFAULT '',
    token_id TEXT NOT NULL DEFAULT '',
    tx_hash TEXT NOT NULL DEFAULT '',
    amount_usd TEXT NOT NULL DEFAULT '',
    required_usdc_raw TEXT NOT NULL DEFAULT '',
    required_weth_raw TEXT NOT NULL DEFAULT '',
    input_mint TEXT NOT NULL DEFAULT '',
    output_mint TEXT NOT NULL DEFAULT '',
    input_amount_raw TEXT NOT NULL DEFAULT '',
    output_amount_raw TEXT NOT NULL DEFAULT '',
    sol_balance_raw TEXT NOT NULL DEFAULT '',
    usdc_balance_raw TEXT NOT NULL DEFAULT '',
    gas_estimate BIGINT NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error_msg TEXT NOT NULL DEFAULT '',
    created_at BIGINT NOT NULL DEFAULT 0,
    updated_at BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_canary_events_created_at
    ON canary_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_canary_events_position
    ON canary_events(position_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_canary_events_tx_hash
    ON canary_events(tx_hash);
