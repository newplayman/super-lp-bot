package tickmath

import (
	"math/big"

	"github.com/lpbot/lpbot/pkg/decimal"
)

// TokenAmounts holds token amounts for a liquidity position.
type TokenAmounts struct {
	Amount0 decimal.Decimal
	Amount1 decimal.Decimal
}

// AmountsForLiquidity computes token amounts given liquidity amount and price range.
// This is the inverse of LiquidityForAmounts.
func AmountsForLiquidity(
	sqrtPriceLowerX96, sqrtPriceUpperX96, sqrtPriceCurrentX96 *big.Int,
	liquidity *big.Int,
) (TokenAmounts, error) {
	tickLower, _ := SqrtPriceX96ToTick(sqrtPriceLowerX96)
	tickUpper, _ := SqrtPriceX96ToTick(sqrtPriceUpperX96)
	tickCurrent, _ := SqrtPriceX96ToTick(sqrtPriceCurrentX96)

	var amount0, amount1 decimal.Decimal

	if tickCurrent < tickLower {
		// Price below range: all amount0
		// amount0 = liquidity * Q96 * (sqrt(upper) - sqrt(lower)) / (sqrt(upper) * sqrt(lower))
		delta := new(big.Int).Sub(sqrtPriceUpperX96, sqrtPriceLowerX96)
		product := new(big.Int).Mul(sqrtPriceUpperX96, sqrtPriceLowerX96)

		// Multiply by Q96 before division to maintain precision
		num := new(big.Int).Mul(liquidity, Q96Big)
		num.Mul(num, delta)
		num.Div(num, product)

		amount0 = decimal.FromBigInt(num)
		amount1 = decimal.Zero
	} else if tickCurrent >= tickUpper {
		// Price above range: all amount1
		// amount1 = liquidity * (sqrt(upper) - sqrt(lower)) / Q96
		delta := new(big.Int).Sub(sqrtPriceUpperX96, sqrtPriceLowerX96)
		num := new(big.Int).Mul(liquidity, delta)
		num.Div(num, Q96Big)

		amount1 = decimal.FromBigInt(num)
		amount0 = decimal.Zero
	} else {
		// In range: split between both
		// amount0 = liquidity * Q96 * (sqrt(upper) - sqrt(current)) / (sqrt(upper) * sqrt(current))
		delta0 := new(big.Int).Sub(sqrtPriceUpperX96, sqrtPriceCurrentX96)
		prod0 := new(big.Int).Mul(sqrtPriceUpperX96, sqrtPriceCurrentX96)
		num0 := new(big.Int).Mul(liquidity, Q96Big)
		num0.Mul(num0, delta0)
		num0.Div(num0, prod0)
		amount0 = decimal.FromBigInt(num0)

		// amount1 = liquidity * (sqrt(current) - sqrt(lower)) / Q96
		delta1 := new(big.Int).Sub(sqrtPriceCurrentX96, sqrtPriceLowerX96)
		num1 := new(big.Int).Mul(liquidity, delta1)
		num1.Div(num1, Q96Big)
		amount1 = decimal.FromBigInt(num1)
	}

	return TokenAmounts{Amount0: amount0, Amount1: amount1}, nil
}
