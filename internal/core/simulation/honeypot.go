package simulation

import (
	"github.com/lpbot/lpbot/internal/domain"
)

// detectHoneypot checks if gas usage suggests honeypot behavior.
// Normal add liquidity operations consume 150k-300k gas.
// A honeypot will consume significantly more gas due to unusual revert patterns.
// Also checks for revert scenarios where success=false.
func detectHoneypot(result *domain.SimulationResult, threshold float64) bool {
	if result == nil {
		return false
	}

	// Check for simulation revert (honeypot indicator)
	if !result.Success {
		return true
	}

	// Expected gas for a normal liquidity operation
	expectedGas := float64(200_000)
	actualGas := float64(result.GasUsed)
	if expectedGas <= 0 {
		return false
	}
	ratio := (actualGas - expectedGas) / expectedGas
	return ratio > threshold
}