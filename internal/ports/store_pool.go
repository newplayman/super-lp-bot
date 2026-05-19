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

// PoolRepo defines the repository interface for pool aggregate persistence.
//
// PoolRepo handles:
//   - pools table: pool metadata with latest Tier/score/audit verdict (UPSERT)
//   - pool_score_history table: per-scan score snapshots (append-only)
//
// The repository is designed for the scanner/audit workflow:
//   1. Scanner scores pools and upserts results
//   2. Each score write appends to score_history
//   3. Audit reads current pool state to perform checks
//   4. Audit updates pool with audit verdict
//
// Implementations must be safe for concurrent use.
type PoolRepo interface {
	// UpsertPool creates or updates pool metadata and current scores.
	//
	// This operation writes to the pools table with:
	//   - Pool fields (ID, Chain, Protocol, Token0, Token1, FeeBPS)
	//   - Current state (Tier_, Liquidity, Tick, TVLUSD, Vol24h, FeeAPR24h)
	//   - UpdatedAt timestamp
	//
	// After upserting, it appends the score to pool_score_history.
	//
	// Returns error if ctx is cancelled or context deadline exceeded.
	UpsertPool(ctx context.Context, pool PoolWithScore) error

	// GetPool retrieves a pool by its unique key: "{chain}:{protocol}:{id}".
	//
	// Returns (pool, nil) if found, (Pool{}, ErrPoolNotFound) if not.
	// Returns error if ctx is cancelled or context deadline exceeded.
	GetPool(ctx context.Context, key string) (domain.Pool, error)

	// ListPools returns pools matching the provided filters.
	//
	// If chain is non-empty, filters to that chain.
	// If tier is non-zero, filters to that tier.
	// If limit > 0, returns at most limit pools (ordered by UpdatedAt DESC).
	// If limit <= 0, uses a default limit.
	//
	// Returns empty slice if no matches (not error).
	ListPools(ctx context.Context, filter PoolFilter) ([]domain.Pool, error)

	// GetScoreHistory returns score history for a pool, ordered by timestamp ASC.
	//
	// limit controls maximum number of entries returned (most recent first).
	// If limit <= 0, returns all available history.
	//
	// Returns empty slice if pool has no history.
	GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]PoolScoreSnapshot, error)

	// UpsertAuditVerdict updates the audit verdict for a pool.
	//
	// Writes the overall verdict and risk score to the pools table.
	// This does NOT append to history (audit findings go to audit_findings table).
	UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error
}

// PoolWithScore holds pool data along with its current score.
type PoolWithScore struct {
	Pool  domain.Pool
	Score domain.Score
}

// PoolFilter specifies criteria for filtering pools.
type PoolFilter struct {
	Chain domain.ChainID // filter by chain (empty = any)
	Tier  domain.Tier     // filter by tier (zero = any)
}

// PoolScoreSnapshot is an immutable record of a pool's score at a point in time.
type PoolScoreSnapshot struct {
	PoolKey  string       // "{chain}:{protocol}:{id}"
	Tier     domain.Tier // tier assigned at this snapshot
	Score    domain.Score
	Timestamp int64       // unix timestamp of the scan
}

// ErrPoolNotFound is returned by GetPool when no matching pool exists.
var ErrPoolNotFound = &PoolNotFoundError{}

type PoolNotFoundError struct{}

func (e *PoolNotFoundError) Error() string   { return "pool not found" }
func (e *PoolNotFoundError) Is(target error) bool {
	_, ok := target.(*PoolNotFoundError)
	return ok
}
