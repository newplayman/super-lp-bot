// Package anvil provides an Anvil-based transaction simulator implementation.
//
// This is a Phase 1 stub that returns mock simulation results.
// Full Anvil fork simulation will be added in a future phase.
package anvil

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// simulator is an Anvil simulator implementation (Phase 1 stub).
type simulator struct{}

// New creates a new Anvil simulator stub.
// The returned simulator returns mock results for all simulation requests.
func New() *simulator {
	return &simulator{}
}

// Simulate implements ports.Simulator.
// Phase 1: Returns a mock successful simulation result.
// TODO(bendu): Implement actual Anvil fork simulation.
func (s *simulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return &domain.SimulationResult{
		Success:  true,
		GasUsed:  100000,
		BlockRef: blockRef,
	}, nil
}

// SimulateSequence implements ports.Simulator.
// Phase 1: Returns mock successful results for all transactions.
// TODO(bendu): Implement actual Anvil fork simulation.
func (s *simulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	results := make([]domain.SimulationResult, len(txs))
	for i := range txs {
		results[i] = domain.SimulationResult{
			Success:  true,
			GasUsed:  100000,
			BlockRef: blockRef,
		}
	}
	return results, nil
}

// Compile-time interface assertion
var _ ports.Simulator = (*simulator)(nil)