package simulation

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// estimateGas calculates the gas estimate with a safety buffer.
// Takes the actual gas used from simulation and adds a buffer for safety.
func estimateGas(gasUsed uint64, buffer decimal.Decimal) domain.Decimal {
	// Convert gas used to decimal
	gasDecimal := decimal.NewFromInt(int64(gasUsed))
	// Add buffer and return
	return gasDecimal.Add(buffer)
}