package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// TxRepo defines the repository interface for transaction aggregate persistence.
//
// TxRepo handles the tx_log table, which tracks the lifecycle of on-chain
// transactions per spec §4.3 (Tx state machine):
//
//	built → broadcast → mined → confirmed
//	            ↘ stuck → rbf_bumped (≤3) → failed
//	            ↘ reverted → failed
//	            ↘ reorged → rebroadcast | manual
//
// Each transition writes to position_history + emits corresponding bus event.
//
// TxRepo is designed for the execution workflow:
//   1. Execution builds and records tx as "built"
//   2. Broadcaster marks as "broadcast"
//   3. Confirmer monitors and updates through mined/confirmed/failed states
//   4. Stuck detection triggers RBF flow
//
// Implementations must be safe for concurrent use.
type TxRepo interface {
	// UpsertTx creates or updates a transaction record.
	//
	// For new transactions, sets status to "built".
	// For existing transactions, updates fields (status, block ref, etc.).
	//
	// The tx is identified by (chain, hash). If hash is empty (local build),
	// the record may use a temporary ID until broadcast.
	//
	// Returns error if ctx is cancelled or context deadline exceeded.
	UpsertTx(ctx context.Context, tx domain.SignedTx) error

	// GetTxByHash retrieves a transaction by its chain and hash.
	//
	// Returns (tx, nil) if found, (SignedTx{}, ErrTxNotFound) if not.
	// Returns error if ctx is cancelled or context deadline exceeded.
	GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error)

	// ListTxsByStatus returns transactions matching the given status.
	//
	// If status is empty, returns all transactions.
	// Results are ordered by CreatedAt DESC (most recent first).
	//
	// Returns empty slice if no matches (not error).
	ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error)

	// UpdateTxStatus transitions a transaction to a new status.
	//
	// Validates the transition using domain.TxStatus.CanTransitionTo().
	// Returns error if the transition is invalid per spec §4.3.
	//
	// Also updates BlockRef if the new status requires it (mined/confirmed/etc.).
	//
	// Returns error if ctx is cancelled, context deadline exceeded, or transition invalid.
	UpdateTxStatus(ctx context.Context, chain domain.ChainID, hash string, newStatus domain.TxStatus, ref *domain.BlockRef) error

	// ListPendingTxs returns transactions that are still in progress.
	//
	// Pending means status is one of: built, broadcast, mined, stuck, rbf_bumped, reverted, reorged.
	// Does NOT include: confirmed, failed, manual.
	//
	// Results are ordered by CreatedAt ASC (oldest first for retry priority).
	//
	// Returns empty slice if no pending transactions.
	ListPendingTxs(ctx context.Context, chain domain.ChainID) ([]domain.SignedTx, error)

	// ListStuckTxs returns transactions that have exceeded the stuck timeout.
	//
	// A tx is "stuck" if status is "broadcast" or "rbf_bumped" and
	// broadcast_at + stuckTimeoutSeconds < current time.
	//
	// These transactions are candidates for RBF bump or manual intervention.
	//
	// Returns empty slice if no stuck transactions.
	ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error)

	// IncrementRFBAttempts increments the RFB attempt counter for a tx.
	//
	// Returns error if tx not found or if attempts would exceed MaxRBFAttempts().
	// Callers should check domain.MaxRBFAttempts() to determine if further RBF is allowed.
	IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error

	// GetRFBAttempts returns the current RFB attempt count for a tx.
	//
	// Returns 0 if tx not found.
	GetRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) (int, error)
}

// TxWithStatus pairs a SignedTx with its current status for display/convenience.
type TxWithStatus struct {
	domain.SignedTx
	Status domain.TxStatus
}

// TxFilter specifies criteria for filtering transactions.
type TxFilter struct {
	Chain domain.ChainID // filter by chain (empty = any)
	Status domain.TxStatus // filter by status (empty = any)
	PoolID string // filter by pool (empty = any)
}

// ErrTxNotFound is returned by GetTxByHash when no matching transaction exists.
var ErrTxNotFound = &TxNotFoundError{}

type TxNotFoundError struct{}

func (e *TxNotFoundError) Error() string   { return "tx not found" }
func (e *TxNotFoundError) Is(target error) bool {
	_, ok := target.(*TxNotFoundError)
	return ok
}

// ErrInvalidTxTransition is returned when a TxStatus transition is not allowed.
var ErrInvalidTxTransition = &InvalidTxTransitionError{}

type InvalidTxTransitionError struct {
	From domain.TxStatus
	To   domain.TxStatus
}

func (e *InvalidTxTransitionError) Error() string {
	return "invalid tx transition: " + string(e.From) + " → " + string(e.To)
}

// ErrMaxRFBAttemptsExceeded is returned when RFB attempts exceed the maximum.
var ErrMaxRFBAttemptsExceeded = &MaxRFBAttemptsExceededError{}

type MaxRFBAttemptsExceededError struct{}

func (e *MaxRFBAttemptsExceededError) Error() string {
	return "max RFB attempts exceeded"
}