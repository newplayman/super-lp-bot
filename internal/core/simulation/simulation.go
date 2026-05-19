// Package simulation provides the core business logic layer for transaction simulation.
//
// This is the Phase 0 scaffold stub implementation where all methods panic.
// Full implementation arrives in Phase 1 (honeypot detection) and Phase 2
// (SimulateSequence for multi-step workflows).
//
// See spec §6.3 for simulator requirements.
package simulation

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/ports"
)

// defaultSimulation is the scaffold stub implementation that panics on use.
// Real implementation will be added in later phases.
//
// In Phase 0, this stub exists only to establish the interface contract
// and allow other modules to compile. Usage in production will panic.
type defaultSimulation struct {
	simulator ports.Simulator
}

// New creates a new Simulator instance.
// In Phase 0, this returns a stub that panics on all operations.
func New(sim ports.Simulator) Simulator {
	return &defaultSimulation{
		simulator: sim,
	}
}

// SimulateAndValidate implements Simulator.
// Phase 1 task: T-102 (honeypot detection integration)
func (s *defaultSimulation) SimulateAndValidate(ctx context.Context, req SimulationRequest) (*SimulationResponse, error) {
	panic(fmt.Sprintf("simulation: defaultSimulation.SimulateAndValidate is a scaffold stub; "+
		"real implementation pending Phase 1. purpose=%s trace=%s", req.Purpose, req.TraceID))
}

// SimulateSequenceAndValidate implements Simulator.
// Phase 2 task: T-201 (multi-step simulation workflows)
func (s *defaultSimulation) SimulateSequenceAndValidate(ctx context.Context, reqs []SimulationRequest) ([]SimulationResponse, error) {
	panic("simulation: defaultSimulation.SimulateSequenceAndValidate is a scaffold stub; " +
		"real implementation pending Phase 2: T-201")
}