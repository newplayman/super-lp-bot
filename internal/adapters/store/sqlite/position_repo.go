// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// PositionRepo implements ports.PositionRepo using SQLite.
type PositionRepo struct {
	db     *sql.DB
	prefix string
}

// NewPositionRepo creates a new PositionRepo backed by the given database.
func NewPositionRepo(db *sql.DB, prefix string) *PositionRepo {
	return &PositionRepo{db: db, prefix: prefix}
}

// Compile-time interface assertion
var _ ports.PositionRepo = (*PositionRepo)(nil)

// Save persists a position. If position exists, it is updated.
func (r *PositionRepo) Save(ctx context.Context, pos *domain.Position) error {
	table := r.prefix + "positions"
	// Schema: id, chain, pool_id, token0, token1, tick_lower, tick_upper,
	//         liquidity, amount0, amount1, tvl_usd, amount_usd, tier,
	//         fee_growth_0, fee_growth_1, collected_fee_0, collected_fee_1,
	//         status, opened_at, updated_at, closed_at
	query := fmt.Sprintf(`
		INSERT INTO %s (
			id, chain, pool_id, token0, token1, tick_lower, tick_upper,
			liquidity, amount0, amount1, tvl_usd, amount_usd, tier,
			status, opened_at, updated_at, closed_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			status = excluded.status,
			tier = excluded.tier,
			amount_usd = excluded.amount_usd,
			tick_lower = excluded.tick_lower,
			tick_upper = excluded.tick_upper,
			amount0 = excluded.amount0,
			amount1 = excluded.amount1,
			updated_at = excluded.updated_at,
			closed_at = excluded.closed_at
	`, table)

	now := time.Now().UnixMilli()

	_, err := r.db.ExecContext(ctx, query,
		pos.ID, string(pos.Chain), pos.PoolID,
		"", "", // token0/token1 placeholder
		pos.TickLower, pos.TickUpper,
		"0", "0", "0", // liquidity/amount0/amount1 placeholder
		"0",                    // tvl_usd placeholder
		pos.AmountUSD.String(), // amount_usd
		string(pos.Tier),       // tier
		string(pos.Status),
		pos.OpenedAt, now, pos.ClosedAt,
	)
	return err
}

// FindByID retrieves a position by its unique identifier.
func (r *PositionRepo) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	table := r.prefix + "positions"
	// Query includes tier and amount_usd
	query := fmt.Sprintf(`
		SELECT id, chain, pool_id, tick_lower, tick_upper, amount0, amount1,
		       amount_usd, tier, status, opened_at, closed_at
		FROM %s WHERE id = ?
	`, table)

	var pos domain.Position
	var chain, status, tier string
	var amountUSDSql sql.NullString
	var openedAt, closedAt int64

	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&pos.ID, &chain, &pos.PoolID,
		&pos.TickLower, &pos.TickUpper,
		new(string), new(string), // amount0, amount1 - ignore
		&amountUSDSql, &tier,
		&status, &openedAt, &closedAt,
	)
	if err == sql.ErrNoRows {
		return nil, ports.ErrPositionNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to find position: %w", err)
	}

	pos.Chain = domain.ChainID(chain)
	pos.Status = domain.PositionStatus(status)
	pos.Tier = domain.Tier(tier)
	if amountUSDSql.Valid {
		pos.AmountUSD, _ = decimal.NewFromString(amountUSDSql.String)
	}
	pos.OpenedAt = openedAt
	pos.ClosedAt = closedAt

	return &pos, nil
}

// FindByPoolAndStatus returns all positions for a given pool with the specified status.
func (r *PositionRepo) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`
		SELECT id, chain, pool_id, tick_lower, tick_upper, amount0, amount1,
		       amount_usd, tier, status, opened_at, closed_at
		FROM %s WHERE pool_id = ? AND status = ?
	`, table)

	rows, err := r.db.QueryContext(ctx, query, poolID, string(status))
	if err != nil {
		return nil, fmt.Errorf("failed to query positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		var pos domain.Position
		var chain, statusStr, tier string
		var amountUSDSql sql.NullString
		var openedAt, closedAt int64

		err := rows.Scan(
			&pos.ID, &chain, &pos.PoolID,
			&pos.TickLower, &pos.TickUpper,
			new(string), new(string), // amount0, amount1
			&amountUSDSql, &tier,
			&statusStr, &openedAt, &closedAt,
		)
		if err != nil {
			continue
		}
		pos.Chain = domain.ChainID(chain)
		pos.Status = domain.PositionStatus(statusStr)
		pos.Tier = domain.Tier(tier)
		if amountUSDSql.Valid {
			pos.AmountUSD, _ = decimal.NewFromString(amountUSDSql.String)
		}
		pos.OpenedAt = openedAt
		pos.ClosedAt = closedAt
		positions = append(positions, &pos)
	}

	return positions, rows.Err()
}

// FindByChainAndStatus returns positions matching chain and status filters.
func (r *PositionRepo) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`
		SELECT id, chain, pool_id, tick_lower, tick_upper, amount0, amount1,
		       amount_usd, tier, status, opened_at, closed_at
		FROM %s WHERE 1=1
	`, table)
	args := []interface{}{}

	if chain != "" {
		query += " AND chain = ?"
		args = append(args, string(chain))
	}
	if status != "" {
		query += " AND status = ?"
		args = append(args, string(status))
	}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		var pos domain.Position
		var chainStr, statusStr, tier string
		var amountUSDSql sql.NullString
		var openedAt, closedAt int64

		err := rows.Scan(
			&pos.ID, &chainStr, &pos.PoolID,
			&pos.TickLower, &pos.TickUpper,
			new(string), new(string), // amount0, amount1
			&amountUSDSql, &tier,
			&statusStr, &openedAt, &closedAt,
		)
		if err != nil {
			continue
		}
		pos.Chain = domain.ChainID(chainStr)
		pos.Status = domain.PositionStatus(statusStr)
		pos.Tier = domain.Tier(tier)
		if amountUSDSql.Valid {
			pos.AmountUSD, _ = decimal.NewFromString(amountUSDSql.String)
		}
		pos.OpenedAt = openedAt
		pos.ClosedAt = closedAt
		positions = append(positions, &pos)
	}

	return positions, rows.Err()
}

// UpdateStatus transitions a position to a new status.
func (r *PositionRepo) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`UPDATE %s
		SET status = ?,
		    updated_at = ?,
		    closed_at = CASE
		        WHEN ? = 'closed' AND closed_at = 0 THEN ?
		        ELSE closed_at
		    END
		WHERE id = ?`, table)
	now := time.Now().UnixMilli()
	closedAt := time.Now().Unix()
	_, err := r.db.ExecContext(ctx, query, string(status), now, string(status), closedAt, id)
	return err
}

// Snapshot returns all positions for a pool without caching (fresh read from DB).
func (r *PositionRepo) Snapshot(ctx context.Context, poolID string) ([]*domain.Position, error) {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`
		SELECT id, chain, pool_id, tick_lower, tick_upper, amount0, amount1,
		       amount_usd, tier, status, opened_at, closed_at
		FROM %s WHERE pool_id = ?
	`, table)

	rows, err := r.db.QueryContext(ctx, query, poolID)
	if err != nil {
		return nil, fmt.Errorf("failed to snapshot positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		var pos domain.Position
		var chain, statusStr, tier string
		var amountUSDSql sql.NullString
		var openedAt, closedAt int64

		err := rows.Scan(
			&pos.ID, &chain, &pos.PoolID,
			&pos.TickLower, &pos.TickUpper,
			new(string), new(string), // amount0, amount1
			&amountUSDSql, &tier,
			&statusStr, &openedAt, &closedAt,
		)
		if err != nil {
			continue
		}
		pos.Chain = domain.ChainID(chain)
		pos.Status = domain.PositionStatus(statusStr)
		pos.Tier = domain.Tier(tier)
		if amountUSDSql.Valid {
			pos.AmountUSD, _ = decimal.NewFromString(amountUSDSql.String)
		}
		pos.OpenedAt = openedAt
		pos.ClosedAt = closedAt
		positions = append(positions, &pos)
	}

	return positions, rows.Err()
}
