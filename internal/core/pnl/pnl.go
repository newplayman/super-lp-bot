package pnl

import (
	"github.com/lpbot/lpbot/internal/domain"
)

// NetPnL computes net profit and loss from component values.
//
// Formula: NetPnL = fees - |IL| - gas
//
// Phase 0 simplification: ignores swap_cost and slippage.
//
// Parameters:
//   - fees: cumulative fee income (non-negative)
//   - il: impermanent loss (should be non-positive)
//   - gas: gas costs (non-negative)
//
// Returns net PnL which can be positive or negative.
func NetPnL(fees, il, gas domain.Decimal) domain.Decimal {
	// IL is typically negative, so il.Abs() gives positive loss
	// NetPnL = fees - |IL| - gas
	return fees.Sub(il.Abs()).Sub(gas)
}

// NetPnLFromComponents computes net PnL from detailed components.
//
// Returns fee + il (where il is negative) = net PnL
// Gas is subtracted separately.
func NetPnLFromComponents(feeUSD, ilUSD, gasUSD domain.Decimal) domain.Decimal {
	return feeUSD.Add(ilUSD).Sub(gasUSD)
}

// NetPnLBreakdown provides a detailed breakdown of PnL components.
type NetPnLBreakdown struct {
	FeeUSD      domain.Decimal
	ILUSD       domain.Decimal
	GasUSD      domain.Decimal
	SwapCostUSD domain.Decimal
	SlippageUSD domain.Decimal
	NetPnLUSD   domain.Decimal
}

// ComputeNetPnL computes full PnL breakdown including all components.
// Phase 0 sets SwapCostUSD and SlippageUSD to zero.
func ComputeNetPnL(
	feeUSD, ilUSD, gasUSD, swapCostUSD, slippageUSD domain.Decimal,
) NetPnLBreakdown {
	netPnL := feeUSD.Add(ilUSD).Sub(gasUSD).Sub(swapCostUSD).Sub(slippageUSD)

	return NetPnLBreakdown{
		FeeUSD:      feeUSD,
		ILUSD:       ilUSD,
		GasUSD:      gasUSD,
		SwapCostUSD: swapCostUSD,
		SlippageUSD: slippageUSD,
		NetPnLUSD:   netPnL,
	}
}