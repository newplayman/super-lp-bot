package il

import "github.com/lpbot/lpbot/pkg/decimal"

// FeeGrowth tracks cumulative fee growth per unit of liquidity.
// Based on Uniswap V3: feeGrowthGlobal0X128, feeGrowthGlobal1X128

// SimFeeGrowth computes fee growth over a time period.
// volumeUSD: trading volume in the pool over the period
// totalLiquidity: pool liquidity amount
// feeTierBPS: fee tier in basis points (e.g., 30 for 0.3%)
func SimFeeGrowth(volumeUSD, totalLiquidity, feeTierBPS decimal.Decimal) decimal.Decimal {
	// fee = volume * fee_tier / total_liquidity
	// feeTier = BPS / 10000 (e.g., 30/10000 = 0.003)
	feeTier := feeTierBPS.MulFrac(1, 10000)
	// Multiply volume by feeTier, then divide by liquidity
	return volumeUSD.Mul(feeTier).MulFrac(1, totalLiquidity.IntPart())
}

// FeeAPR24h: estimated 24h fee APR from volume
// feeVolume24h: fees collected in last 24h (USD)
// tvlUSD: total value locked (USD)
func FeeAPR24h(feeVolume24h, tvlUSD decimal.Decimal) decimal.Decimal {
	if tvlUSD.IsZero() {
		return decimal.Zero
	}
	// Annualize: fee * 365 / tvl
	return feeVolume24h.Mul(decimal.FromInt(365)).MulFrac(1, tvlUSD.IntPart())
}

// UncollectedFees: fees owed to a position since last harvest
// feeGrowthInside: fee growth inside the position's range
// feeGrowthLast: fee growth recorded at last harvest
// liquidity: position liquidity
func UncollectedFees(feeGrowthInside, feeGrowthLast, liquidity decimal.Decimal) decimal.Decimal {
	return feeGrowthInside.Sub(feeGrowthLast).Mul(liquidity)
}