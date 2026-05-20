package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// PositionRepo defines the interface for persisting and retrieving Position aggregates.
// Implementations must be safe for concurrent use.
//
// The repository follows the hexagonal architecture pattern, allowing the core
// business logic to remain independent of the specific storage backend
// (SQLite, PostgreSQL, etc.).
//
// PositionRepo is part of the Store port family per spec §4.4.
type PositionRepo interface {
	// Save persists a position. If a position with the same ID exists, it is updated.
	// Returns an error if the save operation fails.
	Save(ctx context.Context, pos *domain.Position) error

	// FindByID retrieves a position by its unique identifier.
	// Returns nil, nil if the position does not exist.
	FindByID(ctx context.Context, id string) (*domain.Position, error)

	// FindByPoolAndStatus returns all positions for a given pool with the specified status.
	// Used for checking existing positions and invariant #2 (no duplicate open positions per pool).
	FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error)

	// FindByChainAndStatus returns all positions for a given chain with the specified status.
	// Useful for listing all open positions across pools on a chain.
	FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error)

	// UpdateStatus transitions a position to a new status.
	// Valid transitions are defined in domain.PositionStatus.CanTransitionTo.
	// Returns an error if the update fails or the transition is invalid.
	UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error

	// Snapshot returns the current positions for a pool without caching.
	// Used by AllocationManager to check real-time position state.
	// Any error is returned to the caller for fail-closed handling.
	Snapshot(ctx context.Context, poolID string) ([]*domain.Position, error)
}