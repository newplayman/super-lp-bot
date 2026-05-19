package il

import (
	"math/big"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
)

// V3PositionState: snapshot of a V3 LP position
type V3PositionState struct {
	TickLower, TickUpper int64
	Liquidity            *big.Int // raw liquidity amount
	FeeGrowthInside0     decimal.Decimal // cumulative fees inside (token0)
	FeeGrowthInside1     decimal.Decimal // cumulative fees inside (token1)
	Token0, Token1       decimal.Decimal // currently held tokens
}

// V3PositionPnL computes current PnL for a V3 position.
// initialPrice0USD, currentPrice0USD: token0 price in USDC
// returns: {uncollectedFeesUSD, ilUSD, netPnL}
func V3PositionPnL(state V3PositionState, initialPrice0USD, currentPrice0USD decimal.Decimal) (
	uncollectedFeesUSD, ilUSD, netPnL decimal.Decimal,
) {
	// Step 1: Calculate uncollected fees in USD terms
	// Fee value = token0 * currentPrice0USD + token1
	// (token1 is already in USDC)
	feeToken0USD := state.Token0.Mul(currentPrice0USD)
	uncollectedFeesUSD = feeToken0USD.Add(state.Token1)

	// Step 2: Calculate IL
	// For V3 IL calculation, we need the price ratio
	// Convert current price to sqrtPriceX96 for tick comparison
	tickCurrent, err := tickmath.PriceToTick(currentPrice0USD, 6, 6) // USDC/USDC = 1.0
	if err != nil {
		// Fallback: use price ratio directly
		tickCurrent = 0
	}

	// Calculate price ratio: current/initial
	var priceRatio decimal.Decimal
	if initialPrice0USD.IsZero() {
		priceRatio = decimal.FromInt(1)
	} else {
		ratio, _ := currentPrice0USD.Div(initialPrice0USD)
		priceRatio = ratio
	}

	// Get IL based on position relative to price
	var ilPct decimal.Decimal

	// Determine position state based on ticks
	if state.Liquidity != nil && state.Liquidity.Sign() > 0 {
		one := decimal.FromInt(1)
		tickCurrentInt64 := int64(tickCurrent)

		// Calculate sqrt(ratio) for IL formula
		sqrtRatio, _ := priceRatio.Sqrt()

		if tickCurrentInt64 >= state.TickLower && tickCurrentInt64 < state.TickUpper {
			// Case 1: In range. IL = 2*sqrt(r)/(1+r) - 1 (same as V2)
			two := decimal.FromInt(2)
			denom := one.Add(priceRatio)
			num := sqrtRatio.Mul(two)
			ilPct, _ = num.Div(denom)
			ilPct = ilPct.Sub(one)
		} else if tickCurrentInt64 < state.TickLower {
			// Case 2: Below range. IL = sqrt(r) - 1 (negative when r < 1)
			ilPct = sqrtRatio.Sub(one)
		} else {
			// Case 3: Above range. IL = 1/sqrt(r) - 1 (negative when r > 1)
			invSqrt, _ := one.Div(sqrtRatio)
			ilPct = invSqrt.Sub(one)
		}
	} else {
		// No liquidity position - IL is 0 (position closed or not initialized)
		ilPct = decimal.Zero
	}

	// Calculate IL in USD terms
	// IL in USD = IL% * position value (IL% is negative for loss)
	// Position value = token0 * currentPrice + token1 (USDC)
	positionValue := state.Token0.Mul(currentPrice0USD).Add(state.Token1)
	ilUSD = positionValue.Mul(ilPct) // ilUSD will be negative when ilPct is negative

	// Step 3: Net PnL = fees + IL
	// IL is negative (a loss), so adding a negative subtracts from net
	netPnL = uncollectedFeesUSD.Add(ilUSD)

	return
}