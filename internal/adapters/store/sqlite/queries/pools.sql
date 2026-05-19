-- name: UpsertPool :exec
-- Upserts pool metadata with score snapshot.
-- Writes to dryrun_pools table and appends to dryrun_pool_score_history.
INSERT INTO dryrun_pools (
    pool_id, chain, protocol, token0, token1, fee_bps,
    tier, last_score, updated_block, updated_at
) VALUES (
    :pool_id, :chain, :protocol, :token0, :token1, :fee_bps,
    :tier, :last_score, :updated_block, :updated_at
)
ON CONFLICT(pool_id) DO UPDATE SET
    protocol = excluded.protocol,
    token0 = excluded.token0,
    token1 = excluded.token1,
    fee_bps = excluded.fee_bps,
    tier = excluded.tier,
    last_score = excluded.last_score,
    updated_block = excluded.updated_block,
    updated_at = excluded.updated_at;

-- name: InsertPoolScoreHistory :exec
-- Appends a score snapshot to the pool's score history.
INSERT INTO dryrun_pool_score_history (
    pool_id, chain, block_number, block_hash, block_time, score_json, trace_id
) VALUES (
    :pool_id, :chain, :block_number, :block_hash, :block_time, :score_json, :trace_id
);

-- name: GetPool :one
-- Retrieves a single pool by its ID.
-- Returns the pool row or no_rows error.
SELECT
    pool_id, chain, protocol, token0, token1, fee_bps,
    tier, last_score, updated_block, updated_at
FROM dryrun_pools
WHERE pool_id = :pool_id;

-- name: ListPools :many
-- Returns pools filtered by chain, ordered by updated_at DESC.
-- If limit <= 0, uses default limit of 100.
SELECT
    pool_id, chain, protocol, token0, token1, fee_bps,
    tier, last_score, updated_block, updated_at
FROM dryrun_pools
WHERE
    (:chain IS NULL OR chain = :chain)
ORDER BY updated_at DESC
LIMIT :limit;

-- name: GetPoolScoreHistory :many
-- Returns score history for a pool, ordered by block_number DESC.
-- If limit <= 0, returns all available history.
SELECT
    id, pool_id, chain, block_number, block_hash, block_time,
    score_json, trace_id
FROM dryrun_pool_score_history
WHERE pool_id = :pool_id
ORDER BY block_number DESC
LIMIT :limit;

-- name: UpsertAuditVerdict :exec
-- Updates the audit verdict for a pool.
UPDATE dryrun_pools
SET
    tier = :tier,
    audit_verdict = :audit_verdict,
    updated_at = :updated_at
WHERE pool_id = :pool_id;