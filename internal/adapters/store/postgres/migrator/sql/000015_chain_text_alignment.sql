-- +goose Up
-- +goose StatementBegin
-- Phase 3: Chain column type alignment.
--
-- Before this migration:
--   positions.chain             INTEGER
--   pools.chain                 INTEGER
--   pool_score_history.chain    INTEGER
--   pnl_ledger.chain            INTEGER
--   transactions.chain          TEXT
--   execution_intents.chain     TEXT
--   canary_events.chain         TEXT
--   portfolio_snapshots.chain   TEXT
--   shadow_decision_trace.chain TEXT  (000011)
--   shadow_position_marks.chain TEXT  (000013)
--
-- This caused BLK-PG-05 (P0-PG-01 audit): cross-table joins on chain
-- required explicit cast, and the helper chainIDToInt() returned 0 for
-- unknown chains (silent data loss).
--
-- Canonical type: TEXT. Rationale:
--   1. 7 of 10 tables already used TEXT; 3 used INTEGER.
--   2. Shadow tables (in-Go CREATE TABLE) already used TEXT; aligning
--      the rest to TEXT removes the helper-function impedance.
--   3. TEXT preserves the original ChainID value; chainIDToInt() returned
--      0 for "" or unknown chains, silently masking bad data.
--   4. Storage cost is negligible (3-7 bytes per row vs 4 bytes for INT).
--   5. Cross-table joins on chain still require explicit cast in either
--      direction; TEXT is the human-readable choice for a low-cardinality
--      column (currently 2 values: "base", "solana").
--
-- This migration:
--   1. Adds a new column chain_text to each INT-chain table.
--   2. Backfills chain_text from chain via chain int → text mapping
--      (reverse of chainIDToInt in adapter.go).
--   3. Drops the old chain column, renames chain_text → chain.
--   4. Updates affected indexes if any.

-- positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS chain_text TEXT;
UPDATE positions
   SET chain_text = CASE chain
       WHEN 1 THEN 'base' WHEN 2 THEN 'solana' ELSE '' END
 WHERE chain_text IS NULL;
ALTER TABLE positions DROP COLUMN IF EXISTS chain;
ALTER TABLE positions RENAME COLUMN chain_text TO chain;
ALTER TABLE positions ALTER COLUMN chain SET NOT NULL;
ALTER TABLE positions ALTER COLUMN chain SET DEFAULT '';

-- pools
ALTER TABLE pools ADD COLUMN IF NOT EXISTS chain_text TEXT;
UPDATE pools
   SET chain_text = CASE chain
       WHEN 1 THEN 'base' WHEN 2 THEN 'solana' ELSE '' END
 WHERE chain_text IS NULL;
ALTER TABLE pools DROP COLUMN IF EXISTS chain;
ALTER TABLE pools RENAME COLUMN chain_text TO chain;
ALTER TABLE pools ALTER COLUMN chain SET NOT NULL;
ALTER TABLE pools ALTER COLUMN chain SET DEFAULT '';

-- pool_score_history
ALTER TABLE pool_score_history ADD COLUMN IF NOT EXISTS chain_text TEXT;
UPDATE pool_score_history
   SET chain_text = CASE chain
       WHEN 1 THEN 'base' WHEN 2 THEN 'solana' ELSE '' END
 WHERE chain_text IS NULL;
ALTER TABLE pool_score_history DROP COLUMN IF EXISTS chain;
ALTER TABLE pool_score_history RENAME COLUMN chain_text TO chain;
ALTER TABLE pool_score_history ALTER COLUMN chain SET NOT NULL;
ALTER TABLE pool_score_history ALTER COLUMN chain SET DEFAULT '';

-- pnl_ledger
ALTER TABLE pnl_ledger ADD COLUMN IF NOT EXISTS chain_text TEXT;
UPDATE pnl_ledger
   SET chain_text = CASE chain
       WHEN 1 THEN 'base' WHEN 2 THEN 'solana' ELSE '' END
 WHERE chain_text IS NULL;
ALTER TABLE pnl_ledger DROP COLUMN IF EXISTS chain;
ALTER TABLE pnl_ledger RENAME COLUMN chain_text TO chain;
ALTER TABLE pnl_ledger ALTER COLUMN chain SET NOT NULL;
ALTER TABLE pnl_ledger ALTER COLUMN chain SET DEFAULT '';

-- Recreate idx_positions_one_active_per_pool (was dropped implicitly when
-- positions.chain changed type from INTEGER to TEXT). This is the partial
-- unique index that prevents the same pool from having multiple active
-- positions on the same chain — see 000006_active_position_uniqueness.sql
-- and the live schema guard in cmd/lpbot/main.go:821.
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_one_active_per_pool
    ON positions (chain, pool_id)
    WHERE status IN ('intended', 'approved', 'opening', 'open', 'exiting');
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
-- Reverse the alignment: TEXT back to INT (with 0 as default for unknown
-- chains — preserves data integrity at the cost of lossy info for the
-- unknown set).
ALTER TABLE pnl_ledger ADD COLUMN IF NOT EXISTS chain_int INTEGER;
UPDATE pnl_ledger
   SET chain_int = CASE chain
       WHEN 'base' THEN 1 WHEN 'solana' THEN 2 ELSE 0 END
 WHERE chain_int IS NULL;
ALTER TABLE pnl_ledger DROP COLUMN IF EXISTS chain;
ALTER TABLE pnl_ledger RENAME COLUMN chain_int TO chain;
ALTER TABLE pnl_ledger ALTER COLUMN chain SET NOT NULL;
ALTER TABLE pnl_ledger ALTER COLUMN chain SET DEFAULT 0;

ALTER TABLE pool_score_history ADD COLUMN IF NOT EXISTS chain_int INTEGER;
UPDATE pool_score_history
   SET chain_int = CASE chain
       WHEN 'base' THEN 1 WHEN 'solana' THEN 2 ELSE 0 END
 WHERE chain_int IS NULL;
ALTER TABLE pool_score_history DROP COLUMN IF EXISTS chain;
ALTER TABLE pool_score_history RENAME COLUMN chain_int TO chain;
ALTER TABLE pool_score_history ALTER COLUMN chain SET NOT NULL;
ALTER TABLE pool_score_history ALTER COLUMN chain SET DEFAULT 0;

ALTER TABLE pools ADD COLUMN IF NOT EXISTS chain_int INTEGER;
UPDATE pools
   SET chain_int = CASE chain
       WHEN 'base' THEN 1 WHEN 'solana' THEN 2 ELSE 0 END
 WHERE chain_int IS NULL;
ALTER TABLE pools DROP COLUMN IF EXISTS chain;
ALTER TABLE pools RENAME COLUMN chain_int TO chain;
ALTER TABLE pools ALTER COLUMN chain SET NOT NULL;
ALTER TABLE pools ALTER COLUMN chain SET DEFAULT 0;

ALTER TABLE positions ADD COLUMN IF NOT EXISTS chain_int INTEGER;
UPDATE positions
   SET chain_int = CASE chain
       WHEN 'base' THEN 1 WHEN 'solana' THEN 2 ELSE 0 END
 WHERE chain_int IS NULL;
ALTER TABLE positions DROP COLUMN IF EXISTS chain;
ALTER TABLE positions RENAME COLUMN chain_int TO chain;
ALTER TABLE positions ALTER COLUMN chain SET NOT NULL;
ALTER TABLE positions ALTER COLUMN chain SET DEFAULT 0;
-- +goose StatementEnd
