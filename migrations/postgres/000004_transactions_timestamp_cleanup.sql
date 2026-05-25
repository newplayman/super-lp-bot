-- +goose Up
-- +goose StatementBegin

-- Normalize transaction audit timestamps to Unix milliseconds and clear
-- obviously corrupted block numbers from older upsert code.

UPDATE transactions
SET
    created_at = CASE
        WHEN created_at > 0 AND created_at < 2000000000 THEN created_at * 1000
        ELSE created_at
    END,
    updated_at = CASE
        WHEN updated_at > 0 AND updated_at < 2000000000 THEN updated_at * 1000
        ELSE updated_at
    END,
    broadcast_at = CASE
        WHEN broadcast_at > 0 AND broadcast_at < 2000000000 THEN broadcast_at * 1000
        ELSE broadcast_at
    END,
    block_number = CASE
        WHEN block_number > 1000000000 THEN NULL
        ELSE block_number
    END;

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

-- data cleanup migration is not reversible

-- +goose StatementEnd
