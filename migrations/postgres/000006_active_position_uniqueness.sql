CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_one_active_per_pool
    ON positions (chain, pool_id)
    WHERE status IN ('intended', 'approved', 'opening', 'open', 'exiting');
