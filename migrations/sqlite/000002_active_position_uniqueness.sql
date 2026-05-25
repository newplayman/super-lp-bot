-- +goose Up
-- +goose StatementBegin
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_one_active_per_pool
    ON positions (chain, pool_id)
    WHERE status IN ('intended', 'approved', 'opening', 'open', 'exiting');
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP INDEX IF EXISTS idx_positions_one_active_per_pool;
-- +goose StatementEnd
