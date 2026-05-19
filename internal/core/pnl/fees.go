package pnl

import (
	"github.com/lpbot/lpbot/internal/domain"
)

// Swap represents a swap event for fee calculation.
type Swap struct {
	Amount0     domain.Decimal
	Amount1     domain.Decimal
	PoolFeeBPS  uint
}

func AccrueFees(pos domain.Position, swaps []Swap) (domain.Decimal, error) {
	var totalFees domain.Decimal

	for _, swap := range swaps {
		feeTier := domain.NewDecimalFromFloat(float64(swap.PoolFeeBPS) / 10000.0)

		if swap.Amount0.IsNegative() {
			fee1 := swap.Amount1.Abs().Mul(feeTier)
			totalFees = totalFees.Add(fee1)
		} else if swap.Amount1.IsNegative() {
			fee0 := swap.Amount0.Abs().Mul(feeTier)
			totalFees = totalFees.Add(fee0)
		} else {
			fee0 := swap.Amount0.Mul(feeTier)
			fee1 := swap.Amount1.Mul(feeTier)
			totalFees = totalFees.Add(fee0).Add(fee1)
		}
	}

	return totalFees, nil
}

func AccrueFeesFromVolume(volumeUSD domain.Decimal, feeTierBPS uint) domain.Decimal {
	feeTier := domain.NewDecimalFromFloat(float64(feeTierBPS) / 10000.0)
	return volumeUSD.Mul(feeTier)
}