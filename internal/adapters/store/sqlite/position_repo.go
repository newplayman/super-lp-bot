// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
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
	query := fmt.Sprintf(`
		INSERT INTO %s (
			id, chain, pool_id, token0, token1, tick_lower, tick_upper,
			liquidity, amount0, amount1, tvl_usd, status, tier, opened_at, updated_at, closed_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			status = excluded.status,
			tier = excluded.tier,
			updated_at = excluded.updated_at,
			closed_at = excluded.closed_at
	`, table)

	now := time.Now().UnixMilli()

	_, err := r.db.ExecContext(ctx, query,
		pos.ID, string(pos.Chain), pos.PoolID,
		"", "", // token0/token1 not in Position struct
		pos.TickLower, pos.TickUpper,
		"", "", "", // liquidity/amount0/amount1/tvl_usd not in Position struct
		string(pos.Status), string(pos.Tier),
		pos.OpenedAt, now, pos.ClosedAt,
	)
	return err
}

// FindByID retrieves a position by its unique identifier.
func (r *PositionRepo) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`
		SELECT id, chain, pool_id, status, tier, tick_lower, tick_upper, opened_at, updated_at, closed_at
		FROM %s WHERE id = ?
	`, table)

	var pos domain.Position
	var chain, status, tier string
	var openedAt, closedAt int64

	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&pos.ID, &chain, &pos.PoolID, &status, &tier,
		&pos.TickLower, &pos.TickUpper, &openedAt, &closedAt,
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
	pos.OpenedAt = openedAt
	pos.ClosedAt = closedAt

	return &pos, nil
}

// FindByPoolAndStatus returns all positions for a given pool with the specified status.
func (r *PositionRepo) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`SELECT id FROM %s WHERE pool_id = ? AND status = ?`, table)
	args := []interface{}{poolID, string(status)}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query positions: %w", err)
	}
	defer rows.Close()

	var positions []*domain.Position
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			continue
		}
		pos, err := r.FindByID(ctx, id)
		if err == nil {
			positions = append(positions, pos)
		}
	}

	return positions, rows.Err()
}

// FindByChainAndStatus returns positions matching chain and status filters.
func (r *PositionRepo) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`SELECT id FROM %s WHERE 1=1`, table)
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
		var id string
		if err := rows.Scan(&id); err != nil {
			continue
		}
		pos, err := r.FindByID(ctx, id)
		if err == nil {
			positions = append(positions, pos)
		}
	}

	return positions, rows.Err()
}

// UpdateStatus transitions a position to a new status.
func (r *PositionRepo) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	table := r.prefix + "positions"
	query := fmt.Sprintf(`UPDATE %s SET status = ?, updated_at = ? WHERE id = ?`, table)
	now := time.Now().UnixMilli()
	_, err := r.db.ExecContext(ctx, query, string(status), now, id)
	return err
}