// Package ports defines the interface abstractions (hexagonal architecture ports).
//
// The ports layer provides contracts that adapters must satisfy. Core packages
// depend only on these interfaces, never on concrete adapter implementations.
//
// Simulator interface defines the contract for transaction simulation across chains.
package ports

import (
	"github.com/lpbot/lpbot/internal/domain"
)

// Simulator defines the interface for simulating transactions against chain state.
// Used for honeypot detection, slippage verification, and gas estimation
// before transactions are submitted to the blockchain.
//
// Supported chains:
//   - Base / EVM: Anvil fork simulation
//   - Solana: RPC simulateTransaction
//
// Any add/remove/rebalance/exit tx must first pass simulation before being
// admitted by the Risk gate.
type Simulator interface {
	// Simulate executes a single transaction against a forked/pinned block state.
	// Returns the simulation result including success status, gas used, and output amounts.
	//
	// The blockRef pins the execution state (fork URL + fork block number for EVM,
	// or pinned slot for Solana). This ensures deterministic simulation.
	//
	// ctx is the execution context (e.g., context.Context).
	// tx is the unsigned transaction to simulate.
	// blockRef is the block state to fork from.
	//
	// Returns:
	//   - SimulationResult on success (may indicate revert)
	//   - error if simulation could not be performed (e.g., RPC failure)
	Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error)

	// SimulateSequence executes multiple transactions in sequence against the same forked state.
	// The state changes from each transaction persist for subsequent transactions,
	// enabling simulation of complex workflows like:
	//   - Approve → AddLiquidity (two-step open)
	//   - RemoveLiquidity → CollectFees (exit sequence)
	//   - Rebalance: RemoveLiquidity → AddLiquidity (in single block)
	//
	// All transactions must succeed for the simulation to be considered successful.
	// If any transaction reverts, the sequence aborts and returns partial results.
	//
	// ctx is the execution context (e.g., context.Context).
	// txs is the ordered list of transactions to simulate.
	// blockRef is the block state to fork from.
	//
	// Returns:
	//   - Slice of SimulationResult (one per transaction, in order)
	//   - error if simulation could not be performed
	SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error)
}