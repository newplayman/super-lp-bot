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

// ReconStatus represents the result of a reconciliation check.
type ReconStatus string

const (
	ReconPass ReconStatus = "pass"
	ReconFail ReconStatus = "fail"
)

// ReconResult represents the result of comparing on-chain state with local state.
type ReconResult struct {
	// Chain is the blockchain being reconciled.
	Chain domain.ChainID
	// ExpectedCount is the number of positions expected from DB query.
	ExpectedCount int
	// ActualCount is the number of positions found on-chain.
	ActualCount int
	// CountMatch is true if expected == actual.
	CountMatch bool
	// ValueDeviationPct is the percentage deviation in total position value.
	// A value of 0.01 means 1% deviation.
	ValueDeviationPct float64
	// MismatchedPositions lists positions that differ between on-chain and local.
	MismatchedPositions []ReconMismatch
}

// ReconMismatch describes a single position that differs between sources.
type ReconMismatch struct {
	PositionID string
	PoolKey    string
	OnChainUSD float64  // value from chain
	LocalUSD   float64  // value from local DB
	DeviationPct float64 // percentage deviation
}

// ReconciliationLog is a single reconciliation run record (spec §4.2).
//
// reconciliation_log table records the results of bootstrap reconciliation.
// This is an append-only table for audit trail.
type ReconciliationLog struct {
	ID        string       // unique log ID (UUID v7)
	Env       domain.Env   // run mode: dryrun, shadow, live
	Chain     domain.ChainID // blockchain being reconciled
	Status    ReconStatus  // pass or fail
	Result    ReconResult  // detailed result data
	Message   string      // human-readable summary
	Timestamp int64        // unix timestamp
}

// ReconRepo defines the repository interface for reconciliation aggregate persistence.
//
// ReconRepo handles:
//   - reconciliation_log table: startup reconciliation results (append)
//
// The repository is designed for:
//   - Bootstrap reconciliation checking on-chain vs local state (spec §4.6)
//   - Audit trail for reconciliation decisions
//   - Determining whether to enter live mode
//
// Implementations must be safe for concurrent use.
type ReconRepo interface {
	// AppendReconciliationLog appends a new reconciliation result to the audit trail.
	//
	// This operation writes to the reconciliation_log table.
	// Logs are immutable once written (append-only).
	//
	// Returns error if ctx is cancelled or context deadline exceeded.
	AppendReconciliationLog(ctx context.Context, log ReconciliationLog) error

	// ListReconciliationLogs returns reconciliation logs matching the provided filters.
	//
	// If env is non-empty, filters to that specific environment.
	// If chain is non-empty, filters to that specific chain.
	// If status is non-empty, filters to that specific status.
	// If since > 0, filters to logs with timestamp >= since.
	// If limit > 0, returns at most limit logs (ordered by Timestamp DESC).
	//
	// Returns empty slice if no matches (not error).
	ListReconciliationLogs(ctx context.Context, filter ReconLogFilter) ([]ReconciliationLog, error)

	// GetLatestReconciliation returns the most recent reconciliation log for a chain.
	//
	// Returns (log, nil) if found, (ReconciliationLog{}, ErrReconLogNotFound) if not.
	// Returns error if ctx is cancelled or context deadline exceeded.
	GetLatestReconciliation(ctx context.Context, chain domain.ChainID) (ReconciliationLog, error)
}

// ReconLogFilter specifies criteria for filtering reconciliation logs.
type ReconLogFilter struct {
	Env     domain.Env    // filter by environment (empty = any)
	Chain   domain.ChainID // filter by chain (empty = any)
	Status  ReconStatus   // filter by status (empty = any)
	Since   int64         // filter by timestamp >= since (0 = any)
	Limit   int           // maximum results (0 = use default)
}

// ErrReconLogNotFound is returned when a reconciliation log is not found.
var ErrReconLogNotFound = &ReconLogNotFoundError{}

type ReconLogNotFoundError struct{}

func (e *ReconLogNotFoundError) Error() string   { return "reconciliation log not found" }
func (e *ReconLogNotFoundError) Is(target error) bool {
	_, ok := target.(*ReconLogNotFoundError)
	return ok
}
