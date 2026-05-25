-- +goose Up
-- +goose StatementBegin

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS protocol TEXT;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS open_tx_hash TEXT;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

-- additive runtime metadata columns intentionally left in place

-- +goose StatementEnd
