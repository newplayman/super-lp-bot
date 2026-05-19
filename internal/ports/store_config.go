// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// The Store interfaces provide data persistence for domain aggregates.
// Each repository is scoped to a single aggregate type to maintain
// clear boundaries and separation of concerns.
//
// Repository design principles (from spec §4.4):
//   - Aggregate-scoped: PoolRepo, PositionRepo, TxRepo, etc.
//   - sqlc generates query code for two SQL backends (sqlite/postgres)
//   - Handwritten SQL prioritized for audit readability
//   - All monetary values stored as TEXT (decimal strings), never float
package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// ConfigSnapshot represents a stored configuration snapshot (spec §4.2).
//
// config_snapshots table records the full config text and hash at startup.
// This is an append-only table for audit trail (invariant #7).
//
// See spec §2.4 for the three-way config verification:
//   1. build tag ↔ [mode].expected field
//   2. live mode: config hash verification
//   3. config write to snapshots table
type ConfigSnapshot struct {
	ID        string       // unique snapshot ID (UUID v7)
	Env       domain.Env   // run mode: dryrun, shadow, live
	Hash      string       // SHA-256 hash of the config content
	Content   string       // full config TOML content (sanitized of secrets)
	Version   string       // config version identifier
	Timestamp int64        // unix timestamp when snapshot was taken
}

// ConfigSnap defines the repository interface for configuration snapshot persistence.
//
// ConfigSnap handles:
//   - config_snapshots table: startup config full text + hash (append)
//
// The repository is designed for:
//   - Verifying config hasn't changed unexpectedly (invariant #7)
//   - Audit trail for configuration changes
//   - Detecting unauthorized config modifications
//
// Implementations must be safe for concurrent use.
type ConfigSnap interface {
	// AppendSnapshot appends a new config snapshot to the audit trail.
	//
	// This operation writes to the config_snapshots table.
	// Snapshots are immutable once written (append-only).
	//
	// The content should be sanitized to remove sensitive values
	// (passwords, API keys, etc.) before storage.
	//
	// Returns error if ctx is cancelled or context deadline exceeded.
	AppendSnapshot(ctx context.Context, snapshot ConfigSnapshot) error

	// GetLatestSnapshot returns the most recent config snapshot for an environment.
	//
	// Returns (snapshot, nil) if found, (ConfigSnapshot{}, ErrConfigSnapNotFound) if not.
	// Returns error if ctx is cancelled or context deadline exceeded.
	GetLatestSnapshot(ctx context.Context, env domain.Env) (ConfigSnapshot, error)

	// GetPreviousSnapshot returns the second-most-recent config snapshot for comparison.
	//
	// Used to detect unauthorized config changes by comparing hashes.
	// Returns (snapshot, nil) if found, (ConfigSnapshot{}, ErrConfigSnapNotFound) if not.
	// Returns error if ctx is cancelled or context deadline exceeded.
	GetPreviousSnapshot(ctx context.Context, env domain.Env) (ConfigSnapshot, error)

	// ListSnapshots returns config snapshots matching the provided filters.
	//
	// If env is non-empty, filters to that specific environment.
	// If since > 0, filters to snapshots with timestamp >= since.
	// If limit > 0, returns at most limit snapshots (ordered by Timestamp DESC).
	//
	// Returns empty slice if no matches (not error).
	ListSnapshots(ctx context.Context, filter ConfigSnapFilter) ([]ConfigSnapshot, error)
}

// ConfigSnapFilter specifies criteria for filtering config snapshots.
type ConfigSnapFilter struct {
	Env    domain.Env // filter by environment (empty = any)
	Since  int64      // filter by timestamp >= since (0 = any)
	Limit  int         // maximum results (0 = use default)
}

// ErrConfigSnapNotFound is returned when a config snapshot is not found.
var ErrConfigSnapNotFound = &ConfigSnapNotFoundError{}

type ConfigSnapNotFoundError struct{}

func (e *ConfigSnapNotFoundError) Error() string   { return "config snapshot not found" }
func (e *ConfigSnapNotFoundError) Is(target error) bool {
	_, ok := target.(*ConfigSnapNotFoundError)
	return ok
}
