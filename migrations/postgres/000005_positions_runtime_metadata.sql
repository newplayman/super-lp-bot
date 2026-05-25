ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS protocol TEXT;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS open_tx_hash TEXT;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
