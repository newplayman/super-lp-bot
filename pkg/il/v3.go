package il

import (
	"fmt"
	"math/big"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
)

// ILV3 computes V3 impermanent loss based on price range.
// sqrtPrice0X96: initial sqrtPriceX96
// sqrtPriceX96Current: current sqrtPriceX96
// tickLower, tickUpper: the position's tick range
// Returns IL as a decimal (negative = loss, 0 = no change)
//
// Three cases based on current price position:
// 1. Price in range: IL = 2*sqrt(r) / (1 + r) - 1 (same as V2 for in-range positions)
// 2. Price below range: only token0, IL = sqrt(r) - 1 (missed token1 gains)
// 3. Price above range: only token1, IL = 1 - 1/sqrt(r) (missed token0 gains)
func ILV3(sqrtPrice0X96, sqrtPriceX96Current *big.Int, tickLower, tickUpper int64) (decimal.Decimal, error) {
	// Convert sqrtPriceX96 to ticks for comparison
	tickCurrent, err := tickmath.SqrtPriceX96ToTick(sqrtPriceX96Current)
	if err != nil {
		return decimal.Zero, fmt.Errorf("invalid current sqrtPrice: %w", err)
	}
	tickCurrentInt64 := int64(tickCurrent)

	// Convert to decimal for calculation
	// Price = (sqrtPriceX96 / 2^96)^2
	sqrtP0 := decimal.FromBigInt(sqrtPrice0X96)
	sqrtP1 := decimal.FromBigInt(sqrtPriceX96Current)

	// Normalize by Q96 to get sqrt(price)
	q96 := decimal.FromBigInt(tickmath.Q96Big)
	sqrtPrice0, _ := sqrtP0.Div(q96) // sqrt(P0) normalized
	sqrtPrice1, _ := sqrtP1.Div(q96)  // sqrt(P1) normalized

	// Calculate price ratio P1/P0 = (sqrt(P1)/sqrt(P0))^2
	sqrtRatio, _ := sqrtPrice1.Div(sqrtPrice0)
	priceRatio := sqrtRatio.Mul(sqrtRatio)

	one := decimal.FromInt(1)

	if tickCurrentInt64 >= tickLower && tickCurrentInt64 < tickUpper {
		// Case 1: Price in range
		// IL = 2*sqrt(r) / (1 + r) - 1
		sqrtRatioVal, err := priceRatio.Sqrt()
		if err != nil {
			return decimal.Zero, err
		}
		num := sqrtRatioVal.Mul(decimal.FromInt(2))
		denom := one.Add(priceRatio)
		ilFactor, err := num.Div(denom)
		if err != nil {
			return decimal.Zero, err
		}
		il := ilFactor.Sub(one)
		return il, nil
	}

	// Case 2: Price below range (only token0 in LP)
	// IL = sqrt(r) - 1 (negative when r < 1)
	if tickCurrentInt64 < tickLower {
		sqrtRatioVal, err := priceRatio.Sqrt()
		if err != nil {
			return decimal.Zero, err
		}
		il := sqrtRatioVal.Sub(one)
		return il, nil
	}

	// Case 3: Price above range (only token1 in LP)
	// IL = 1/sqrt(r) - 1 (negative when r > 1)
	sqrtRatioVal, err := priceRatio.Sqrt()
	if err != nil {
		return decimal.Zero, err
	}
	invSqrt, err := one.Div(sqrtRatioVal)
	if err != nil {
		return decimal.Zero, err
	}
	il := invSqrt.Sub(one)
	return il, nil
}