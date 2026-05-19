// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// PoolRepo implements ports.PoolRepo using SQLite.
type PoolRepo struct {
	db *sql.DB
}

// NewPoolRepo creates a new PoolRepo backed by the given database connection.
func NewPoolRepo(db *sql.DB) *PoolRepo {
	return &PoolRepo{db: db}
}

// Compile-time interface assertion
var _ ports.PoolRepo = (*PoolRepo)(nil)

// UpsertPool creates or updates pool metadata and current scores.
// This writes to the pools table and appends a score history entry.
func (r *PoolRepo) UpsertPool(ctx context.Context, pool ports.PoolWithScore) error {
	// Serialize score to JSON for storage
	scoreJSON, err := json.Marshal(pool.Score)
	if err != nil {
		return fmt.Errorf("failed to marshal score: %w", err)
	}

	// Use transaction to ensure atomicity
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	// Upsert pool (INSERT OR REPLACE)
	_, err = tx.ExecContext(ctx, `
		INSERT INTO dryrun_pools (
			pool_id, chain, protocol, token0, token1, fee_bps,
			tier, audit_verdict, last_score, updated_block, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(pool_id) DO UPDATE SET
			chain = excluded.chain,
			protocol = excluded.protocol,
			token0 = excluded.token0,
			token1 = excluded.token1,
			fee_bps = excluded.fee_bps,
			tier = excluded.tier,
			audit_verdict = excluded.audit_verdict,
			last_score = excluded.last_score,
			updated_block = excluded.updated_block,
			updated_at = excluded.updated_at
	`,
		pool.Pool.ID,
		chainIDToInt(pool.Pool.Chain),
		pool.Pool.Protocol,
		pool.Pool.Token0.String(),
		pool.Pool.Token1.String(),
		pool.Pool.FeeBPS,
		string(pool.Pool.Tier_),
		"", // audit_verdict set separately via UpsertAuditVerdict
		string(scoreJSON),
		0,  // updated_block - could be extended to track this
		pool.Pool.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert pool: %w", err)
	}

	// Append score history entry
	_, err = tx.ExecContext(ctx, `
		INSERT INTO dryrun_pool_score_history (
			pool_id, chain, block_number, block_hash, block_time,
			score_json, trace_id
		) VALUES (?, ?, ?, ?, ?, ?, ?)
	`,
		pool.Pool.ID,
		chainIDToInt(pool.Pool.Chain),
		0, // block_number - could be extended
		"", // block_hash
		pool.Pool.UpdatedAt,
		string(scoreJSON),
		"", // trace_id - could be extended
	)
	if err != nil {
		return fmt.Errorf("failed to insert score history: %w", err)
	}

	return tx.Commit()
}

// GetPool retrieves a pool by its unique key: "{chain}:{protocol}:{id}".
func (r *PoolRepo) GetPool(ctx context.Context, key string) (domain.Pool, error) {
	// Parse the key into chain, protocol, and id
	parts := strings.SplitN(key, ":", 3)
	if len(parts) != 3 {
		return domain.Pool{}, fmt.Errorf("invalid pool key format: %q (expected {chain}:{protocol}:{id})", key)
	}

	chain, err := domain.ParseChainID(parts[0])
	if err != nil {
		return domain.Pool{}, fmt.Errorf("invalid chain in pool key: %w", err)
	}
	protocol := parts[1]
	poolID := parts[2]

	// Query the pool
	var row struct {
		ID           string
		Chain        int
		Protocol     string
		Token0       string
		Token1       string
		FeeBPS       int
		Tier         sql.NullString
		AuditVerdict sql.NullString
		LastScore    sql.NullString
		UpdatedBlock int
		UpdatedAt    int64
	}

	err = r.db.QueryRowContext(ctx, `
		SELECT pool_id, chain, protocol, token0, token1, fee_bps,
		       tier, audit_verdict, last_score, updated_block, updated_at
		FROM dryrun_pools
		WHERE pool_id = ? AND chain = ? AND protocol = ?
	`, poolID, chainIDToInt(chain), protocol).Scan(
		&row.ID, &row.Chain, &row.Protocol,
		&row.Token0, &row.Token1, &row.FeeBPS,
		&row.Tier, &row.AuditVerdict, &row.LastScore,
		&row.UpdatedBlock, &row.UpdatedAt,
	)
	if err == sql.ErrNoRows {
		return domain.Pool{}, ports.ErrPoolNotFound
	}
	if err != nil {
		return domain.Pool{}, fmt.Errorf("failed to query pool: %w", err)
	}

	// Build Pool entity
	token0, err := domain.ParseAddress(row.Token0)
	if err != nil {
		return domain.Pool{}, fmt.Errorf("failed to parse token0 address: %w", err)
	}
	token1, err := domain.ParseAddress(row.Token1)
	if err != nil {
		return domain.Pool{}, fmt.Errorf("failed to parse token1 address: %w", err)
	}

	var tier domain.Tier
	if row.Tier.Valid {
		tier = domain.Tier(row.Tier.String)
	}

	pool := domain.Pool{
		ID:        row.ID,
		Chain:     intToChainID(row.Chain),
		Protocol:  row.Protocol,
		Token0:    token0,
		Token1:    token1,
		FeeBPS:    uint(row.FeeBPS),
		Tier_:     tier,
		UpdatedAt: row.UpdatedAt,
	}

	// Parse last_score JSON to extract additional fields
	if row.LastScore.Valid {
		var score domain.Score
		if err := json.Unmarshal([]byte(row.LastScore.String), &score); err == nil {
			// Tier may be derived from score if not stored
			if tier == "" {
				pool.Tier_ = score.AssignTier()
			}
		}
	}

	return pool, nil
}

// ListPools returns pools matching the provided filters.
func (r *PoolRepo) ListPools(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error) {
	// Build query with optional filters
	query := `
		SELECT pool_id, chain, protocol, token0, token1, fee_bps,
		       tier, audit_verdict, last_score, updated_block, updated_at
		FROM dryrun_pools
		WHERE 1=1
	`
	args := []interface{}{}

	if filter.Chain != "" {
		query += " AND chain = ?"
		args = append(args, chainIDToInt(filter.Chain))
	}

	if filter.Tier != "" {
		query += " AND tier = ?"
		args = append(args, string(filter.Tier))
	}

	query += " ORDER BY updated_at DESC"

	// Apply limit
	limit := filter.Limit
	if limit <= 0 {
		limit = 100 // default limit
	}
	query += " LIMIT ?"
	args = append(args, limit)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list pools: %w", err)
	}
	defer rows.Close()

	var pools []domain.Pool
	for rows.Next() {
		var row struct {
			ID           string
			Chain        int
			Protocol     string
			Token0       string
			Token1       string
			FeeBPS       int
			Tier         sql.NullString
			AuditVerdict sql.NullString
			LastScore    sql.NullString
			UpdatedBlock int
			UpdatedAt    int64
		}

		err := rows.Scan(
			&row.ID, &row.Chain, &row.Protocol,
			&row.Token0, &row.Token1, &row.FeeBPS,
			&row.Tier, &row.AuditVerdict, &row.LastScore,
			&row.UpdatedBlock, &row.UpdatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan pool row: %w", err)
		}

		token0, err := domain.ParseAddress(row.Token0)
		if err != nil {
			continue // skip malformed rows
		}
		token1, err := domain.ParseAddress(row.Token1)
		if err != nil {
			continue
		}

		var tier domain.Tier
		if row.Tier.Valid {
			tier = domain.Tier(row.Tier.String)
		}

		pool := domain.Pool{
			ID:        row.ID,
			Chain:     intToChainID(row.Chain),
			Protocol:  row.Protocol,
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    uint(row.FeeBPS),
			Tier_:     tier,
			UpdatedAt: row.UpdatedAt,
		}

		// Parse last_score JSON
		if row.LastScore.Valid {
			var score domain.Score
			if err := json.Unmarshal([]byte(row.LastScore.String), &score); err == nil {
				if tier == "" {
					pool.Tier_ = score.AssignTier()
				}
			}
		}

		pools = append(pools, pool)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating pool rows: %w", err)
	}

	return pools, nil
}

// GetScoreHistory returns score history for a pool, ordered by timestamp ASC.
func (r *PoolRepo) GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]ports.PoolScoreSnapshot, error) {
	// Parse the key
	parts := strings.SplitN(poolKey, ":", 3)
	if len(parts) != 3 {
		return nil, fmt.Errorf("invalid pool key format: %q", poolKey)
	}

	chain, err := domain.ParseChainID(parts[0])
	if err != nil {
		return nil, fmt.Errorf("invalid chain in pool key: %w", err)
	}
	protocol := parts[1]
	poolID := parts[2]

	// Build query
	query := `
		SELECT pool_id, block_time, score_json
		FROM dryrun_pool_score_history
		WHERE pool_id = ? AND chain = ?
		ORDER BY block_time ASC
	`
	if limit > 0 {
		query += " LIMIT ?"
	}

	args := []interface{}{poolID, chainIDToInt(chain)}
	if limit > 0 {
		args = append(args, limit)
	}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query score history: %w", err)
	}
	defer rows.Close()

	var snapshots []ports.PoolScoreSnapshot
	for rows.Next() {
		var poolID string
		var blockTime int64
		var scoreJSON string

		err := rows.Scan(&poolID, &blockTime, &scoreJSON)
		if err != nil {
			return nil, fmt.Errorf("failed to scan history row: %w", err)
		}

		var score domain.Score
		if err := json.Unmarshal([]byte(scoreJSON), &score); err != nil {
			continue // skip malformed JSON
		}

		snapshots = append(snapshots, ports.PoolScoreSnapshot{
			PoolKey:  fmt.Sprintf("%s:%s:%s", chain, protocol, poolID),
			Tier:     score.AssignTier(),
			Score:    score,
			Timestamp: blockTime,
		})
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating history rows: %w", err)
	}

	return snapshots, nil
}

// UpsertAuditVerdict updates the audit verdict for a pool.
func (r *PoolRepo) UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error {
	// Parse the key
	parts := strings.SplitN(poolKey, ":", 3)
	if len(parts) != 3 {
		return fmt.Errorf("invalid pool key format: %q", poolKey)
	}

	chain, err := domain.ParseChainID(parts[0])
	if err != nil {
		return fmt.Errorf("invalid chain in pool key: %w", err)
	}
	protocol := parts[1]
	poolID := parts[2]

	// Update the pool's audit verdict
	result, err := r.db.ExecContext(ctx, `
		UPDATE dryrun_pools
		SET audit_verdict = ?, updated_at = ?
		WHERE pool_id = ? AND chain = ? AND protocol = ?
	`, string(verdict), 0, poolID, chainIDToInt(chain), protocol)
	if err != nil {
		return fmt.Errorf("failed to update audit verdict: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return ports.ErrPoolNotFound
	}

	return nil
}

// chainIDToInt converts a ChainID to its integer representation.
func chainIDToInt(chain domain.ChainID) int {
	switch chain {
	case domain.ChainBase:
		return 0
	case domain.ChainSolana:
		return 1
	default:
		return -1
	}
}

// intToChainID converts an integer back to ChainID.
func intToChainID(n int) domain.ChainID {
	switch n {
	case 0:
		return domain.ChainBase
	case 1:
		return domain.ChainSolana
	default:
		return domain.ChainID(fmt.Sprintf("unknown(%d)", n))
	}
}