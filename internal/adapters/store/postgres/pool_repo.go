// Package postgres provides PostgreSQL-backed storage adapters for lp-bot.
package postgres

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// PoolRepo implements ports.PoolRepo using PostgreSQL.
type PoolRepo struct {
	db *sql.DB
}

// NewPoolRepo creates a new PoolRepo backed by the given database.
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

	// Upsert pool
	_, err = tx.ExecContext(ctx, `
		INSERT INTO pools (
			pool_id, chain, protocol, token0, token1, fee_bps,
			tier, audit_verdict, last_score, updated_block, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
		ON CONFLICT (pool_id, chain, protocol) DO UPDATE SET
			token0 = excluded.token0,
			token1 = excluded.token1,
			fee_bps = excluded.fee_bps,
			tier = excluded.tier,
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
		scoreJSON,
		0, // updated_block
		pool.Pool.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert pool: %w", err)
	}

	// Append score history entry
	_, err = tx.ExecContext(ctx, `
		INSERT INTO pool_score_history (
			pool_id, chain, block_number, block_hash, block_time,
			score_json, trace_id
		) VALUES ($1, $2, $3, $4, $5, $6, $7)
	`,
		pool.Pool.ID,
		chainIDToInt(pool.Pool.Chain),
		0, // block_number
		"", // block_hash
		pool.Pool.UpdatedAt,
		scoreJSON,
		"", // trace_id
	)
	if err != nil {
		return fmt.Errorf("failed to insert score history: %w", err)
	}

	return tx.Commit()
}

// GetPool retrieves a pool by its unique key: "{chain}:{protocol}:{id}".
func (r *PoolRepo) GetPool(ctx context.Context, key string) (domain.Pool, error) {
	parts := strings.SplitN(key, ":", 3)
	if len(parts) != 3 {
		return domain.Pool{}, fmt.Errorf("invalid pool key format: %q", key)
	}

	chain, err := domain.ParseChainID(parts[0])
	if err != nil {
		return domain.Pool{}, fmt.Errorf("invalid chain in pool key: %w", err)
	}
	protocol := parts[1]
	poolID := parts[2]

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
		FROM pools
		WHERE pool_id = $1 AND chain = $2 AND protocol = $3
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

	token0, err := domain.ParseAddress(row.Token0)
	if err != nil {
		return domain.Pool{}, fmt.Errorf("failed to parse token0 address: %w", err)
	}
	token1, err := domain.ParseAddress(row.Token1)
	if err != nil {
		return domain.Pool{}, fmt.Errorf("failed to parse token1 address: %w", err)
	}

	pool := domain.Pool{
		ID:        row.ID,
		Chain:     intToChainID(row.Chain),
		Protocol:  row.Protocol,
		Token0:    token0,
		Token1:    token1,
		FeeBPS:    uint(row.FeeBPS),
		UpdatedAt: row.UpdatedAt,
	}

	if row.Tier.Valid {
		pool.Tier_ = domain.Tier(row.Tier.String)
	}

	return pool, nil
}

// ListPools returns pools matching the provided filters.
func (r *PoolRepo) ListPools(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error) {
	query := `
		SELECT pool_id, chain, protocol, token0, token1, fee_bps,
		       tier, audit_verdict, last_score, updated_block, updated_at
		FROM pools
		WHERE 1=1
	`
	args := []interface{}{}

	if filter.Chain != "" {
		query += " AND chain = $1"
		args = append(args, chainIDToInt(filter.Chain))
		filterIdx := 2
		if filter.Tier != "" {
			query += fmt.Sprintf(" AND tier = $%d", filterIdx)
			args = append(args, string(filter.Tier))
		}
	} else if filter.Tier != "" {
		query += " AND tier = $1"
		args = append(args, string(filter.Tier))
	}

	query += " ORDER BY updated_at DESC"

	limit := filter.Limit
	if limit <= 0 {
		limit = 100
	}
	query += fmt.Sprintf(" LIMIT $%d", len(args)+1)
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
			continue
		}
		token1, err := domain.ParseAddress(row.Token1)
		if err != nil {
			continue
		}

		pool := domain.Pool{
			ID:        row.ID,
			Chain:     intToChainID(row.Chain),
			Protocol:  row.Protocol,
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    uint(row.FeeBPS),
			UpdatedAt: row.UpdatedAt,
		}

		if row.Tier.Valid {
			pool.Tier_ = domain.Tier(row.Tier.String)
		}

		pools = append(pools, pool)
	}

	return pools, rows.Err()
}

// GetScoreHistory returns score history for a pool.
func (r *PoolRepo) GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]ports.PoolScoreSnapshot, error) {
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

	query := `
		SELECT pool_id, block_time, score_json
		FROM pool_score_history
		WHERE pool_id = $1 AND chain = $2
		ORDER BY block_time ASC
	`
	args := []interface{}{poolID, chainIDToInt(chain)}

	if limit > 0 {
		query += fmt.Sprintf(" LIMIT $%d", 3)
		args = append(args, limit)
	}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query score history: %w", err)
	}
	defer rows.Close()

	var snapshots []ports.PoolScoreSnapshot
	for rows.Next() {
		var rowPoolID string
		var blockTime int64
		var scoreJSON string

		err := rows.Scan(&rowPoolID, &blockTime, &scoreJSON)
		if err != nil {
			return nil, fmt.Errorf("failed to scan history row: %w", err)
		}

		score, err := parseScoreFromJSON(scoreJSON)
		if err != nil {
			continue
		}

		snapshots = append(snapshots, ports.PoolScoreSnapshot{
			PoolKey:   fmt.Sprintf("%s:%s:%s", chain, protocol, rowPoolID),
			Tier:      score.AssignTier(),
			Score:     score,
			Timestamp: blockTime,
		})
	}

	return snapshots, rows.Err()
}

// UpsertAuditVerdict updates the audit verdict for a pool.
func (r *PoolRepo) UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error {
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

	result, err := r.db.ExecContext(ctx, `
		UPDATE pools
		SET audit_verdict = $1, updated_at = $2
		WHERE pool_id = $3 AND chain = $4 AND protocol = $5
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

// parseScoreFromJSON parses a Score from JSON string.
func parseScoreFromJSON(jsonStr string) (domain.Score, error) {
	var score domain.Score
	if jsonStr == "" {
		return score, fmt.Errorf("empty JSON")
	}
	if err := json.Unmarshal([]byte(jsonStr), &score); err != nil {
		return domain.Score{}, fmt.Errorf("failed to parse score JSON: %w", err)
	}
	// Compute total if not set
	if score.Total == 0 {
		score.Total = score.ComputeTotal()
	}
	return score, nil
}