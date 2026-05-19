// Package simulation provides the core business logic layer for transaction simulation.
//
// This module wraps the ports.Simulator interface with business rules for:
//   - Honeypot detection (spec §6.3)
//   - Slippage validation (spec §6.4)
//   - Gas estimation before Risk gate admission
//
// Any add/remove/rebalance/exit tx must first pass simulation before being
// admitted by the Risk gate (spec invariant).
//
// See spec §6.3 for simulator requirements per chain:
//   - Base / EVM: Anvil fork simulation
//   - Solana: RPC simulateTransaction
package simulation

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// SimulationRequest encapsulates a transaction simulation request with metadata.
type SimulationRequest struct {
	// Tx is the unsigned transaction to simulate.
	Tx domain.UnsignedTx
	// BlockRef pins the execution state for deterministic simulation.
	BlockRef domain.BlockRef
	// TraceID links this simulation to the broader decision flow.
	TraceID string
	// Purpose describes why this simulation is needed (e.g., "honeypot_check", "gas_estimate").
	Purpose string
}

// SimulationResponse contains the simulation result with business-level annotations.
type SimulationResponse struct {
	// Result is the raw simulation result from the simulator.
	Result *domain.SimulationResult
	// HoneypotDetected indicates if the simulation revealed honeypot behavior.
	HoneypotDetected bool
	// SlippageValid indicates if slippage was within acceptable bounds.
	SlippageValid bool
	// GasEstimate is the estimated gas cost in native token.
	GasEstimate domain.Decimal
}

// Simulator defines the interface for transaction simulation in the core layer.
// Unlike ports.Simulator which is the raw interface, this interface adds
// business-level checks (honeypot detection, slippage validation).
type Simulator interface {
	// SimulateAndValidate runs a simulation with business-level validation.
	// It wraps ports.Simulator.Simulate with:
	//   - Honeypot detection: flagging transactions with unusual revert patterns
	//   - Slippage validation: checking output amounts against MinOut
	//
	// Returns a SimulationResponse with annotated results.
	// Returns error only on system failures (RPC errors, etc.), not on simulation reverts.
	SimulateAndValidate(ctx context.Context, req SimulationRequest) (*SimulationResponse, error)

	// SimulateSequenceAndValidate runs multiple simulations with business-level validation.
	// State persists across transactions in the sequence.
	// Returns annotated results for each transaction in order.
	SimulateSequenceAndValidate(ctx context.Context, reqs []SimulationRequest) ([]SimulationResponse, error)
}

// Compile-time assertion: Simulator interface must be satisfied.
var _ Simulator = (*defaultSimulation)(nil)