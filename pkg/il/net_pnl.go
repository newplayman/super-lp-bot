package il

import (
	"math/big"

	"github.com/lpbot/lpbot/pkg/decimal"
)

// NetPnL combines IL + fees into a single net PnL figure (excluding gas costs).
// This is a unified interface that works for both V2 and V3 positions.
//
// For V2: uses simple price-ratio IL formula
// For V3: uses tick-range-aware IL formula
//
// Returns: {feeUSD, ilUSD, netPnL} where:
//   - feeUSD >= 0 (fee income, always non-negative)
//   - ilUSD <= 0 (IL loss, always non-positive)
//   - netPnL = feeUSD + ilUSD (can be positive or negative)
func NetPnL(v2 bool, state any, initialPriceUSD, currentPriceUSD decimal.Decimal, feeVolume24h, tvlUSD decimal.Decimal) (feeUSD, ilUSD, netPnL decimal.Decimal, _ error) {
	if v2 {
		return netPnLV2(state.(V2PositionState), initialPriceUSD, currentPriceUSD, feeVolume24h, tvlUSD)
	}
	return netPnLV3(state.(V3PositionState), initialPriceUSD, currentPriceUSD)
}

func netPnLV2(state V2PositionState, initialPriceUSD, currentPriceUSD, feeVolume24h, tvlUSD decimal.Decimal) (feeUSD, ilUSD, netPnL decimal.Decimal, _ error) {
	feeUSD, ilUSD, netPnL = V2PositionPnL(state, currentPriceUSD, feeVolume24h, tvlUSD)
	return feeUSD, ilUSD, netPnL, nil
}

func netPnLV3(state V3PositionState, initialPriceUSD, currentPriceUSD decimal.Decimal) (feeUSD, ilUSD, netPnL decimal.Decimal, _ error) {
	feeUSD, ilUSD, netPnL = V3PositionPnL(state, initialPriceUSD, currentPriceUSD)
	return feeUSD, ilUSD, netPnL, nil
}

// NetPnLForTokenAmounts computes net PnL from raw token amounts (no pool state needed).
// This is useful when you only have token balances and prices.
//
// positionValueUSD: current value of position in USD
// initialPriceUSD: price when position was opened
// currentPriceUSD: current price
// sqrtPrice0X96: initial sqrtPriceX96 (for V3)
// sqrtPriceCurrentX96: current sqrtPriceX96 (for V3)
// tickLower, tickUpper: V3 tick range (ignored for V2)
// feeGrowth: cumulative fee growth
// feeGrowthLast: last checkpoint fee growth
// liquidity: position liquidity (for V3)
func NetPnLForTokenAmounts(
	v2 bool,
	positionValueUSD, initialPriceUSD, currentPriceUSD decimal.Decimal,
	sqrtPrice0X96, sqrtPriceCurrentX96 *big.Int,
	tickLower, tickUpper int64,
	feeGrowth, feeGrowthLast, liquidity decimal.Decimal,
) (feeUSD, ilUSD, netPnL decimal.Decimal, _ error) {
	// Calculate IL
	var ilPct decimal.Decimal
	if v2 {
		ilPct = ILV2(initialPriceUSD, currentPriceUSD)
	} else {
		var err error
		ilPct, err = ILV3(sqrtPrice0X96, sqrtPriceCurrentX96, tickLower, tickUpper)
		if err != nil {
			return decimal.Zero, decimal.Zero, decimal.Zero, err
		}
	}
	ilUSD = positionValueUSD.Mul(ilPct)

	// Calculate fee income (V3: uncollected fees = (feeGrowth - feeGrowthLast) * liquidity)
	var fee decimal.Decimal
	if v2 {
		fee = decimal.Zero // V2 fee calculated at pool level
	} else {
		diff := feeGrowth.Sub(feeGrowthLast)
		fee = diff.Mul(liquidity)
	}
	feeUSD = fee

	// Net PnL = fee - |IL| = fee + il (il is negative)
	netPnL = feeUSD.Add(ilUSD)

	return feeUSD, ilUSD, netPnL, nil
}