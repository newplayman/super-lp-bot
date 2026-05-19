package simulation

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// validateSlippage checks if output amounts are within acceptable slippage bounds.
// It compares the actual output against the minimum output specified in the transaction.
func validateSlippage(outputs []domain.TokenAmount, minOut domain.Decimal, maxBps int) bool {
	if minOut.IsZero() {
		return false
	}

	// Calculate total output value (sum of all output amounts)
	var totalOutput domain.Decimal
	for _, output := range outputs {
		totalOutput = totalOutput.Add(output.Amount)
	}

	// Calculate slippage percentage
	slippage := minOut.Sub(totalOutput).Div(minOut)
	slippageBps := slippage.Mul(decimal.NewFromInt(10000))
	return slippageBps.LessThanOrEqual(decimal.NewFromInt(int64(maxBps)))
}