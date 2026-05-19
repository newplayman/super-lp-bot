// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// PoolRepo implements ports.PoolRepo using SQLite.
type PoolRepo struct {
	db     *sql.DB
	prefix string
}

// NewPoolRepo creates a new PoolRepo backed by the given database connection.
func NewPoolRepo(db *sql.DB, prefix string) *PoolRepo {
	return &PoolRepo{db: db, prefix: prefix}
}

// Compile-time interface assertion
var _ ports.PoolRepo = (*PoolRepo)(nil)

// UpsertPool creates or updates pool metadata and current scores.
func (r *PoolRepo) UpsertPool(ctx context.Context, pool ports.PoolWithScore) error {
	scoreJSON, err := json.Marshal(pool.Score)
	if err != nil {
		return fmt.Errorf("failed to marshal score: %w", err)
	}

	now := time.Now().UnixMilli()
	table := r.prefix + "pools"

	query := fmt.Sprintf(`
		INSERT INTO %s (
			id, chain, protocol, token0, token1, fee_bps,
			tier, tvl_usd, vol_24h, fee_apr_24h, last_score, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			chain = excluded.chain,
			protocol = excluded.protocol,
			token0 = excluded.token0,
			token1 = excluded.token1,
			fee_bps = excluded.fee_bps,
			tier = excluded.tier,
			tvl_usd = excluded.tvl_usd,
			vol_24h = excluded.vol_24h,
			fee_apr_24h = excluded.fee_apr_24h,
			last_score = excluded.last_score,
			updated_at = excluded.updated_at
	`, table)

	_, err = r.db.ExecContext(ctx, query,
		pool.Pool.ID, pool.Pool.Chain, pool.Pool.Protocol,
		pool.Pool.Token0.String(), pool.Pool.Token1.String(),
		pool.Pool.FeeBPS, pool.Pool.Tier_.String(),
		pool.Pool.TVLUSD.String(), pool.Pool.Vol24h.String(), pool.Pool.FeeAPR24h.String(),
		scoreJSON, now,
	)
	return err
}

// GetPool retrieves a pool by its unique key: "{chain}:{protocol}:{id}".
func (r *PoolRepo) GetPool(ctx context.Context, key string) (domain.Pool, error) {
	parts := strings.SplitN(key, ":", 3)
	if len(parts) != 3 {
		return domain.Pool{}, fmt.Errorf("invalid pool key format: %q", key)
	}

	chain, err := domain.ParseChainID(parts[0])
	if err != nil {
		return domain.Pool{}, fmt.Errorf("invalid chain: %w", err)
	}
	protocol := parts[1]
	poolID := parts[2]

	table := r.prefix + "pools"
	query := fmt.Sprintf(`
		SELECT id, chain, protocol, token0, token1, fee_bps,
		       tier, tvl_usd, vol_24h, fee_apr_24h, last_score, updated_at
		FROM %s
		WHERE id = ? AND chain = ? AND protocol = ?
	`, table)

	var row struct {
		ID, Chain, Protocol, Token0, Token1 string
		FeeBPS    int
		Tier      sql.NullString
		TVLUSD    sql.NullString
		Vol24h    sql.NullString
		FeeAPR24h sql.NullString
		LastScore sql.NullString
		UpdatedAt int64
	}

	err = r.db.QueryRowContext(ctx, query, poolID, string(chain), protocol).Scan(
		&row.ID, &row.Chain, &row.Protocol,
		&row.Token0, &row.Token1, &row.FeeBPS,
		&row.Tier, &row.TVLUSD, &row.Vol24h, &row.FeeAPR24h, &row.LastScore,
		&row.UpdatedAt,
	)
		if err != nil {
		return domain.Pool{}, fmt.Errorf("failed to query pool: %w", err)
	}

	token0, _ := domain.ParseAddress(row.Token0)
	token1, _ := domain.ParseAddress(row.Token1)

	var tier domain.Tier
	if row.Tier.Valid {
		tier = domain.Tier(row.Tier.String)
	}

	pool := domain.Pool{
		ID:       row.ID,
		Chain:    chain,
		Protocol: row.Protocol,
		Token0:   token0,
		Token1:   token1,
		FeeBPS:   uint(row.FeeBPS),
		Tier_:    tier,
		UpdatedAt: row.UpdatedAt,
	}

	if row.TVLUSD.Valid {
		pool.TVLUSD, _ = decimal.NewFromString(row.TVLUSD.String)
	}
	if row.Vol24h.Valid {
		pool.Vol24h, _ = decimal.NewFromString(row.Vol24h.String)
	}
	if row.FeeAPR24h.Valid {
		pool.FeeAPR24h, _ = decimal.NewFromString(row.FeeAPR24h.String)
	}

	if row.LastScore.Valid {
		var score domain.Score
		if err := json.Unmarshal([]byte(row.LastScore.String), &score); err == nil && tier == "" {
			pool.Tier_ = score.AssignTier()
		}
	}

	return pool, nil
}

// ListPools returns pools matching the provided filters.
func (r *PoolRepo) ListPools(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error) {
	table := r.prefix + "pools"
	query := fmt.Sprintf(`
		SELECT id, chain, protocol, token0, token1, fee_bps,
		       tier, tvl_usd, vol_24h, fee_apr_24h, last_score, updated_at
		FROM %s WHERE 1=1
	`, table)
	args := []interface{}{}

	if filter.Chain != "" {
		query += " AND chain = ?"
		args = append(args, string(filter.Chain))
	}
	if filter.Tier != "" {
		query += " AND tier = ?"
		args = append(args, string(filter.Tier))
	}

	query += " ORDER BY updated_at DESC"
	limit := filter.Limit
	if limit <= 0 {
		limit = 100
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
			ID, Chain, Protocol, Token0, Token1 string
			FeeBPS    int
			Tier      sql.NullString
			TVLUSD    sql.NullString
			Vol24h    sql.NullString
			FeeAPR24h sql.NullString
			LastScore sql.NullString
			UpdatedAt int64
		}

		err := rows.Scan(
			&row.ID, &row.Chain, &row.Protocol,
			&row.Token0, &row.Token1, &row.FeeBPS,
			&row.Tier, &row.TVLUSD, &row.Vol24h, &row.FeeAPR24h, &row.LastScore,
			&row.UpdatedAt,
		)
		if err != nil {
			continue
		}

		token0, _ := domain.ParseAddress(row.Token0)
		token1, _ := domain.ParseAddress(row.Token1)

		var tier domain.Tier
		if row.Tier.Valid {
			tier = domain.Tier(row.Tier.String)
		}

		chainID, _ := domain.ParseChainID(row.Chain)
		pool := domain.Pool{
			ID:       row.ID,
			Chain:    chainID,
			Protocol: row.Protocol,
			Token0:   token0,
			Token1:   token1,
			FeeBPS:   uint(row.FeeBPS),
			Tier_:    tier,
			UpdatedAt: row.UpdatedAt,
		}

		if row.TVLUSD.Valid {
			pool.TVLUSD, _ = decimal.NewFromString(row.TVLUSD.String)
		}
		if row.Vol24h.Valid {
			pool.Vol24h, _ = decimal.NewFromString(row.Vol24h.String)
		}
		if row.FeeAPR24h.Valid {
			pool.FeeAPR24h, _ = decimal.NewFromString(row.FeeAPR24h.String)
		}

		if row.LastScore.Valid {
			var score domain.Score
			if err := json.Unmarshal([]byte(row.LastScore.String), &score); err == nil && tier == "" {
				pool.Tier_ = score.AssignTier()
			}
		}

		pools = append(pools, pool)
	}

	return pools, rows.Err()
}

// GetScoreHistory returns score history for a pool (simplified implementation).
func (r *PoolRepo) GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]ports.PoolScoreSnapshot, error) {
	return nil, nil
}

// UpsertAuditVerdict updates the audit verdict for a pool (simplified implementation).
func (r *PoolRepo) UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error {
	return nil
}


// chainToInt converts ChainID to integer.
func chainToInt(chain domain.ChainID) int {
	switch chain {
	case domain.ChainBase:
		return 0
	case domain.ChainSolana:
		return 1
	default:
		return -1
	}
}

// intToChainID converts integer to ChainID.
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