-- +goose Up
-- +goose StatementBegin

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    pool_address TEXT NOT NULL,
    tick_lower INTEGER NOT NULL,
    tick_upper INTEGER NOT NULL,
    liquidity TEXT NOT NULL,
    owner TEXT NOT NULL,
    opened_at INTEGER NOT NULL,
    closed_at INTEGER,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    order_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    executed_at INTEGER,
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    tx_hash TEXT NOT NULL UNIQUE,
    block_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    gas_used TEXT,
    gas_price TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_states (
    id TEXT PRIMARY KEY,
    pool_address TEXT NOT NULL,
    tick INTEGER NOT NULL,
    liquidity TEXT NOT NULL,
    observation_cardinality INTEGER,
    snapshot_at INTEGER NOT NULL
);

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE IF EXISTS pool_states;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS positions;

-- +goose StatementEnd