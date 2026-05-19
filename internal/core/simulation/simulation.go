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

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// SimulationConfig holds configuration for simulation behavior.
type SimulationConfig struct {
	MaxSlippageBps    int             // Maximum slippage allowed in basis points
	HoneypotThreshold float64         // Threshold ratio for honeypot detection
	GasEstimateBuffer decimal.Decimal // Buffer added to gas estimate for safety
}

// DefaultSimulationConfig returns the default simulation configuration.
func DefaultSimulationConfig() SimulationConfig {
	return SimulationConfig{
		MaxSlippageBps:    50,             // 0.5% default max slippage
		HoneypotThreshold: 0.1,            // 10% gas over expected triggers honeypot
		GasEstimateBuffer: decimal.NewFromInt(1_200_000),
	}
}

// defaultSimulation is the core implementation of Simulator.
type defaultSimulation struct {
	simulator ports.Simulator
	config    SimulationConfig
}

// New creates a new Simulator instance with the given port and config.
func New(sim ports.Simulator, cfg SimulationConfig) Simulator {
	return &defaultSimulation{
		simulator: sim,
		config:    cfg,
	}
}

// SimulateAndValidate implements Simulator.
func (s *defaultSimulation) SimulateAndValidate(ctx context.Context, req SimulationRequest) (*SimulationResponse, error) {
	result, err := s.simulator.Simulate(ctx, req.Tx, req.BlockRef)
	if err != nil {
		return nil, err
	}

	resp := &SimulationResponse{Result: result}
	resp.HoneypotDetected = detectHoneypot(result, s.config.HoneypotThreshold)
	if result != nil && result.OutputAmounts != nil {
		resp.SlippageValid = validateSlippage(result.OutputAmounts, req.Tx.MinOut, s.config.MaxSlippageBps)
	}
	if result != nil {
		resp.GasEstimate = estimateGas(result.GasUsed, s.config.GasEstimateBuffer)
	}
	return resp, nil
}

// SimulateSequenceAndValidate implements Simulator.
func (s *defaultSimulation) SimulateSequenceAndValidate(ctx context.Context, reqs []SimulationRequest) ([]SimulationResponse, error) {
	// TODO: implement sequence validation
	return nil, nil
}