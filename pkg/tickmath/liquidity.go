package tickmath

import (
	"errors"
	"math/big"

	"github.com/lpbot/lpbot/pkg/decimal"
)

// LiquidityForAmounts computes the liquidity amount given desired token amounts
// and a price range.
func LiquidityForAmounts(
	sqrtPriceLowerX96, sqrtPriceUpperX96, sqrtPriceCurrentX96 *big.Int,
	amount0, amount1 decimal.Decimal,
) (*big.Int, error) {
	if sqrtPriceUpperX96.Cmp(sqrtPriceLowerX96) <= 0 {
		return nil, errors.New("upper price must be greater than lower price")
	}

	sqrtA, _ := SqrtPriceX96ToTick(sqrtPriceLowerX96)
	sqrtB, _ := SqrtPriceX96ToTick(sqrtPriceUpperX96)
	sqrtP, _ := SqrtPriceX96ToTick(sqrtPriceCurrentX96)

	var liquidity *big.Int

	if sqrtP < sqrtA {
		num := new(big.Int).Mul(sqrtPriceUpperX96, sqrtPriceLowerX96)
		denom := new(big.Int).Sub(sqrtPriceUpperX96, sqrtPriceLowerX96)
		liquidity = amount0BI(amount0)
		liquidity.Mul(liquidity, num)
		liquidity.Div(liquidity, denom)
		liquidity.Div(liquidity, Q96Big)
	} else if sqrtP >= sqrtB {
		liquidity = amount1BI(amount1)
		liquidity.Mul(liquidity, Q96Big)
		denom := new(big.Int).Sub(sqrtPriceUpperX96, sqrtPriceLowerX96)
		liquidity.Div(liquidity, denom)
	} else {
		l0, _ := liquidity0(sqrtPriceLowerX96, sqrtPriceCurrentX96, sqrtPriceUpperX96, amount0BI(amount0))
		l1, _ := liquidity1(sqrtPriceLowerX96, sqrtPriceCurrentX96, sqrtPriceUpperX96, amount1BI(amount1))
		if l0.Cmp(l1) < 0 {
			liquidity = l0
		} else {
			liquidity = l1
		}
	}

	return liquidity, nil
}

func liquidity0(sqrtALower, sqrtPCurr, sqrtBUpper, amount0 *big.Int) (*big.Int, error) {
	delta := new(big.Int).Sub(sqrtBUpper, sqrtALower)
	num := new(big.Int).Mul(sqrtBUpper, sqrtALower)
	num.Mul(num, amount0)
	denom := new(big.Int).Mul(delta, Q96Big)
	return new(big.Int).Div(num, denom), nil
}

func liquidity1(sqrtALower, sqrtPCurr, sqrtBUpper, amount1 *big.Int) (*big.Int, error) {
	delta := new(big.Int).Sub(sqrtBUpper, sqrtALower)
	num := new(big.Int).Mul(amount1, Q96Big)
	return new(big.Int).Div(num, delta), nil
}

func amount0BI(d decimal.Decimal) *big.Int {
	v, _ := new(big.Int).SetString(d.String(), 10)
	return v
}

func amount1BI(d decimal.Decimal) *big.Int {
	return amount0BI(d)
}
