// Package sol_rpc provides a Solana RPC-based transaction simulator implementation.
//
// This is a Phase 1 stub that returns mock simulation results.
// Full Solana RPC simulateTransaction will be added in a future phase.
package sol_rpc

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// simulator is a Solana RPC simulator implementation (Phase 1 stub).
type simulator struct{}

// New creates a new Solana RPC simulator stub.
// The returned simulator returns mock results for all simulation requests.
func New() *simulator {
	return &simulator{}
}

// Simulate implements ports.Simulator.
// Phase 1: Returns a mock successful simulation result.
// TODO(bendu): Implement actual Solana RPC simulateTransaction.
func (s *simulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return &domain.SimulationResult{
		Success:  true,
		BlockRef: blockRef,
	}, nil
}

// SimulateSequence implements ports.Simulator.
// Phase 1: Returns mock successful results for all transactions.
// TODO(bendu): Implement actual Solana RPC simulateTransaction.
func (s *simulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	results := make([]domain.SimulationResult, len(txs))
	for i := range txs {
		results[i] = domain.SimulationResult{
			Success:  true,
			BlockRef: blockRef,
		}
	}
	return results, nil
}

// Compile-time interface assertion
var _ ports.Simulator = (*simulator)(nil)