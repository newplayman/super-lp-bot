// Package postgres provides PostgreSQL-backed storage adapters for lp-bot.
package postgres

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// PositionRepo implements ports.PositionRepo using PostgreSQL.
type PositionRepo struct {
	db *sql.DB
}

// NewPositionRepo creates a new PositionRepo backed by the given database.
func NewPositionRepo(db *sql.DB) *PositionRepo {
	return &PositionRepo{db: db}
}

// Compile-time interface assertion
var _ ports.PositionRepo = (*PositionRepo)(nil)

// Save persists a position. If a position with the same ID exists, it is updated.
func (r *PositionRepo) Save(ctx context.Context, pos *domain.Position) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO positions (
			id, token_id, pool_id, chain, status, tier, tick_lower, tick_upper,
			amount_usd, opened_at, closed_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
		ON CONFLICT (id) DO UPDATE SET
			token_id = excluded.token_id,
			status = excluded.status,
			tier = excluded.tier,
			tick_lower = excluded.tick_lower,
			tick_upper = excluded.tick_upper,
			amount_usd = excluded.amount_usd,
			closed_at = excluded.closed_at
	`,
		pos.ID,
		pos.TokenID,
		pos.PoolID,
		chainIDToInt(pos.Chain),
		string(pos.Status),
		string(pos.Tier),
		pos.TickLower,
		pos.TickUpper,
		pos.AmountUSD.String(),
		pos.OpenedAt,
		pos.ClosedAt,
	)
	if err != nil {
		return fmt.Errorf("failed to save position: %w", err)
	}
	return nil
}

// FindByID retrieves a position by its unique identifier.
func (r *PositionRepo) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	var row struct {
		ID        string
		TokenID   string
		PoolID    string
		Chain     int
		Status    string
		Tier      string
		TickLower int64
		TickUpper int64
		AmountUSD string
		OpenedAt  int64
		ClosedAt  int64
	}

	err := r.db.QueryRowContext(ctx, `
		SELECT id, COALESCE(token_id, ''), pool_id, chain, status, tier, tick_lower, tick_upper,
		       amount_usd, opened_at, COALESCE(closed_at, 0)
		FROM positions
		WHERE id = $1
	`, id).Scan(
		&row.ID, &row.TokenID, &row.PoolID, &row.Chain, &row.Status, &row.Tier,
		&row.TickLower, &row.TickUpper, &row.AmountUSD,
		&row.OpenedAt, &row.ClosedAt,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query position: %w", err)
	}

	tier, _ := domain.ParseTier(row.Tier)
	pos := &domain.Position{
		ID:        row.ID,
		TokenID:   row.TokenID,
		PoolID:    row.PoolID,
		Chain:     intToChainID(row.Chain),
		Status:    domain.PositionStatus(row.Status),
		Tier:      tier,
		TickLower: row.TickLower,
		TickUpper: row.TickUpper,
		OpenedAt:  row.OpenedAt,
		ClosedAt:  row.ClosedAt,
	}

	if row.AmountUSD != "" {
		pos.AmountUSD = domain.MustDecimal(row.AmountUSD)
	}

	return pos, nil
}

// FindByPoolAndStatus returns all positions for a pool with the specified status.
func (r *PositionRepo) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, COALESCE(token_id, ''), pool_id, chain, status, tier, tick_lower, tick_upper,
		       amount_usd, opened_at, COALESCE(closed_at, 0)
		FROM positions
		WHERE pool_id = $1 AND status = $2
	`, poolID, string(status))
	if err != nil {
		return nil, fmt.Errorf("failed to query positions: %w", err)
	}
	defer rows.Close()

	return scanPositions(rows)
}

// FindByChainAndStatus returns all positions for a chain with the specified status.
func (r *PositionRepo) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, COALESCE(token_id, ''), pool_id, chain, status, tier, tick_lower, tick_upper,
		       amount_usd, opened_at, COALESCE(closed_at, 0)
		FROM positions
		WHERE chain = $1 AND status = $2
	`, chainIDToInt(chain), string(status))
	if err != nil {
		return nil, fmt.Errorf("failed to query positions: %w", err)
	}
	defer rows.Close()

	return scanPositions(rows)
}

// UpdateStatus transitions a position to a new status.
func (r *PositionRepo) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	result, err := r.db.ExecContext(ctx, `
		UPDATE positions
		SET status = $1,
		    closed_at = CASE
		        WHEN $1 = 'closed' AND closed_at = 0 THEN EXTRACT(EPOCH FROM NOW())::BIGINT
		        ELSE closed_at
		    END
		WHERE id = $2
	`, string(status), id)
	if err != nil {
		return fmt.Errorf("failed to update position status: %w", err)
	}

	rows, _ := result.RowsAffected()
	if rows == 0 {
		return fmt.Errorf("position not found: %s", id)
	}
	return nil
}

// Snapshot returns all positions for a pool without caching (fresh read from DB).
func (r *PositionRepo) Snapshot(ctx context.Context, poolID string) ([]*domain.Position, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, COALESCE(token_id, ''), pool_id, chain, status, tier, tick_lower, tick_upper,
		       amount_usd, opened_at, COALESCE(closed_at, 0)
		FROM positions
		WHERE pool_id = $1
	`, poolID)
	if err != nil {
		return nil, fmt.Errorf("failed to snapshot positions: %w", err)
	}
	defer rows.Close()

	return scanPositions(rows)
}

// scanPositions scans rows into Position slice.
func scanPositions(rows *sql.Rows) ([]*domain.Position, error) {
	var positions []*domain.Position
	for rows.Next() {
		var row struct {
			ID        string
			TokenID   string
			PoolID    string
			Chain     int
			Status    string
			Tier      string
			TickLower int64
			TickUpper int64
			AmountUSD string
			OpenedAt  int64
			ClosedAt  int64
		}

		err := rows.Scan(
			&row.ID, &row.TokenID, &row.PoolID, &row.Chain, &row.Status, &row.Tier,
			&row.TickLower, &row.TickUpper, &row.AmountUSD,
			&row.OpenedAt, &row.ClosedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan position row: %w", err)
		}

		tier, _ := domain.ParseTier(row.Tier)
		pos := &domain.Position{
			ID:        row.ID,
			TokenID:   row.TokenID,
			PoolID:    row.PoolID,
			Chain:     intToChainID(row.Chain),
			Status:    domain.PositionStatus(row.Status),
			Tier:      tier,
			TickLower: row.TickLower,
			TickUpper: row.TickUpper,
			OpenedAt:  row.OpenedAt,
			ClosedAt:  row.ClosedAt,
		}

		if row.AmountUSD != "" {
			pos.AmountUSD = domain.MustDecimal(row.AmountUSD)
		}

		positions = append(positions, pos)
	}

	return positions, rows.Err()
}
