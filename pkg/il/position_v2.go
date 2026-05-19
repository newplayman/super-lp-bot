package il

import "github.com/lpbot/lpbot/pkg/decimal"

// V2PositionState: V2 LP position snapshot
type V2PositionState struct {
	Reserve0, Reserve1  decimal.Decimal // current pool reserves
	Amount0, Amount1     decimal.Decimal // LP's token holdings
	InitialPrice0USD     decimal.Decimal // price0 at position open
}

// V2PositionPnL computes current PnL for a V2 position.
// currentPrice0USD: token0 current USDC price
// feeVolume24h: past 24h trading volume (for fee estimation)
// tvlUSD: pool TVL
// returns: {feeUSD, ilUSD, netPnL}
func V2PositionPnL(state V2PositionState, currentPrice0USD, feeVolume24h, tvlUSD decimal.Decimal) (
	feeUSD, ilUSD, netPnL decimal.Decimal,
) {
	// Calculate current LP position value in USD
	// token0 value + token1 value (token1 is in USDC)
	lpValueUSD := state.Amount0.Mul(currentPrice0USD).Add(state.Amount1)

	// Calculate IL using V2 formula
	// IL = ILV2(initialPrice0USD, currentPrice0USD)
	ilPct := ILV2(state.InitialPrice0USD, currentPrice0USD)

	// IL in USD: ilPct * lpValueUSD (ilPct is negative for loss)
	ilUSD = lpValueUSD.Mul(ilPct)

	// Calculate fee income based on liquidity share
	// fee share = position_liquidity / pool_liquidity
	// We estimate position liquidity from reserves and amounts
	var liquidityShare decimal.Decimal

	if !state.Reserve0.IsZero() || !state.Reserve1.IsZero() {
		// Estimate pool total value
		poolValueUSD := state.Reserve0.Mul(currentPrice0USD).Add(state.Reserve1)

		if !poolValueUSD.IsZero() {
			// Liquidity share = position_value / pool_value
			share, _ := lpValueUSD.Div(poolValueUSD)
			liquidityShare = share
		}
	}

	// Fee income = feeVolume24h * liquidity_share
	feeUSD = feeVolume24h.Mul(liquidityShare)

	// Net PnL = fee - IL (IL is already negative)
	// If IL is -100 and fee is +50, net = 50 + (-100) = -50
	netPnL = feeUSD.Add(ilUSD)

	return
}