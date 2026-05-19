// Package execution implements the OrderManager pattern for transaction execution.
// It orchestrates the full lifecycle from approved position intents to confirmed
// on-chain transactions.
//
// See spec §6.4 for architecture details and module README for bus integration.
package execution

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// ExecutionResult holds the outcome of an execution attempt.
type ExecutionResult struct {
	// TxHash is the transaction hash if the transaction was broadcast.
	// Empty if execution was not attempted or failed before broadcast.
	TxHash string

	// Success indicates whether the execution completed successfully.
	Success bool

	// Error is the error message if execution failed.
	Error string

	// PositionID is the associated position ID for the execution.
	PositionID string

	// FinalStatus is the terminal status of the position after execution.
	FinalStatus domain.PositionStatus
}

// OpenIntent represents an intent to open a new position.
type OpenIntent struct {
	// PositionID is the unique identifier for this position.
	PositionID string

	// PoolID is the pool to provide liquidity to.
	PoolID string

	// Chain is the target chain.
	Chain domain.ChainID

	// Tier is the risk tier of the position.
	Tier domain.Tier

	// AmountUSD is the position size in USD.
	AmountUSD domain.Decimal

	// TickLower is the lower tick boundary (V3).
	TickLower int64

	// TickUpper is the upper tick boundary (V3).
	TickUpper int64

	// Simulation is the result of pre-execution simulation.
	Simulation *domain.SimulationResult

	// TraceID traces the intent through the decision pipeline.
	TraceID string
}

// ExitIntent represents an intent to close an existing position.
type ExitIntent struct {
	// PositionID is the position to close.
	PositionID string

	// Chain is the target chain.
	Chain domain.ChainID

	// Simulation is the result of pre-execution simulation.
	Simulation *domain.SimulationResult

	// TraceID traces the intent through the decision pipeline.
	TraceID string

	// Reason is the reason for the exit (stop_loss, rebalance, manual, etc.).
	Reason string
}

// RebalanceIntent represents an intent to rebalance an existing position.
type RebalanceIntent struct {
	// PositionID is the position to rebalance.
	PositionID string

	// Chain is the target chain.
	Chain domain.ChainID

	// NewTickLower is the new lower tick boundary.
	NewTickLower int64

	// NewTickUpper is the new upper tick boundary.
	NewTickUpper int64

	// Simulation is the result of pre-execution simulation.
	Simulation *domain.SimulationResult

	// TraceID traces the intent through the decision pipeline.
	TraceID string
}

// ExecutionConfig holds configuration for the execution module.
type ExecutionConfig struct {
	// StuckTimeout is the duration after which a pending tx is considered stuck.
	StuckTimeout int64 // seconds

	// MaxRBFAttempts is the maximum number of RBF attempts for stuck transactions.
	MaxRBFAttempts int

	// RequiredConfirmations is the number of block confirmations required.
	RequiredConfirmations int
}

// DefaultExecutionConfig returns the default execution configuration.
func DefaultExecutionConfig() ExecutionConfig {
	return ExecutionConfig{
		StuckTimeout:          300, // 5 minutes
		MaxRBFAttempts:        3,
		RequiredConfirmations: 1,
	}
}

// OrderManager defines the interface for orchestrating position execution.
// It consumes approved intents and manages the full transaction lifecycle.
//
// OrderManager responsibilities (spec §6.4):
//
//   - Orchestrate: intent → Risk.Admit → Simulator → TxBuilder → Approve → Signer → MEV → Confirmer
//   - Manage transaction state machine (built → broadcast → mined → confirmed)
//   - Handle nonce management and RBF for stuck transactions
//   - Emit bus events for position state transitions
//
// Thread safety: implementations must be safe for concurrent use.
type OrderManager interface {
	// Open executes an approved position opening intent.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - intent: the approved opening intent (must pass Risk gate first)
	//
	// Returns an ExecutionResult with the outcome.
	//
	// The intent's Simulation field should contain a valid simulation result
	// from Simulator.Simulate before calling Open. The simulation validates
	// the transaction would succeed and checks for honeypots.
	//
	// Invariants enforced:
	//   - MinOut and Deadline in Simulation.OutputAmounts must be non-zero (#4)
	//   - dryrun mode: broadcast must never be called (#3)
	//
	// Bus events published:
	//   - <env>.tx.broadcast on successful broadcast
	//   - <env>.position.opened on successful confirmation
	//   - <env>.tx.failed on failure
	Open(ctx context.Context, intent OpenIntent) ExecutionResult

	// Close executes an approved position exit.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - intent: the approved exit intent
	//
	// Returns an ExecutionResult with the outcome.
	//
	// Invariants enforced:
	//   - Token approvals must be revoked after close (#10)
	//   - MinOut and Deadline must be non-zero (#4)
	//
	// Bus events published:
	//   - <env>.tx.broadcast on successful broadcast
	//   - <env>.position.closed on successful confirmation
	//   - <env>.tx.failed on failure
	Close(ctx context.Context, intent ExitIntent) ExecutionResult

	// Rebalance executes an approved position rebalance.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - intent: the approved rebalance intent
	//
	// Returns an ExecutionResult with the outcome.
	//
	// Rebalance removes liquidity at current range and adds at new range
	// in a coordinated manner to minimize price exposure during transition.
	Rebalance(ctx context.Context, intent RebalanceIntent) ExecutionResult

	// CollectFees collects accumulated fees from a position without closing.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - positionID: the position to collect fees from
	//
	// Returns an ExecutionResult with the outcome.
	// The transaction hash will be populated on successful broadcast.
	CollectFees(ctx context.Context, positionID string) ExecutionResult

	// UpdateTxStatus updates the status of a tracked transaction.
	//
	// Parameters:
	//   - txHash: the transaction hash
	//   - status: the new status
	//
	// This is called by the Confirmer to update transaction state.
	// State machine transitions are validated per domain.TxValidTransitions.
	UpdateTxStatus(ctx context.Context, txHash string, status domain.TxStatus) error

	// GetPendingTxs returns all transactions that are still pending.
	// Used by Watchdog for stuck transaction monitoring.
	GetPendingTxs(ctx context.Context) ([]domain.SignedTx, error)

	// RetryStuck retries a stuck transaction with RBF if possible.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - txHash: the stuck transaction hash
	//
	// Returns an ExecutionResult with the outcome.
	// Returns an error if RBF is not possible (max attempts exceeded).
	RetryStuck(ctx context.Context, txHash string) (ExecutionResult, error)

	// Config returns the current execution configuration.
	Config() ExecutionConfig
}

// ExecutionDependencies holds the ports required by OrderManager.
type ExecutionDependencies struct {
	// Chain provides blockchain interaction capabilities.
	Chain ports.Chain

	// EVMChain provides EVM-specific capabilities (nonce, gas).
	// May be nil for Solana-only execution.
	EVMChain ports.EVMChain

	// SolanaChain provides Solana-specific capabilities.
	// May be nil for EVM-only execution.
	SolanaChain ports.SolanaChain

	// Wallet provides transaction signing capabilities.
	Wallet ports.Wallet

	// Broadcaster broadcasts signed transactions to the network.
	Broadcaster ports.Broadcaster

	// MEVSubmitter provides MEV-protected submission.
	// May be nil in dryrun/shadow builds (compile-time absent).
	MEVSubmitter ports.MEVSubmitter

	// Bus provides event publishing and subscription.
	Bus ports.Bus
}