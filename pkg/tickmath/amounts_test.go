package tickmath_test

import (
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

func TestAmountsForLiquidity_Roundtrip(t *testing.T) {
	// Given liquidity, sqrt prices, we should be able to recover token amounts
	sqrtLower, _ := tickmath.TickToSqrtPriceX96(-1000)
	sqrtUpper, _ := tickmath.TickToSqrtPriceX96(1000)
	sqrtCurrent, _ := tickmath.TickToSqrtPriceX96(0)

	amt0 := decimal.MustFromString("1000000")
	amt1 := decimal.MustFromString("1000000")

	lq, err := tickmath.LiquidityForAmounts(sqrtLower, sqrtUpper, sqrtCurrent, amt0, amt1)
	require.NoError(t, err)
	require.True(t, lq.BitLen() > 0)

	// Now reverse: amounts from liquidity
	result, err := tickmath.AmountsForLiquidity(sqrtLower, sqrtUpper, sqrtCurrent, lq)
	require.NoError(t, err)
	// Result amounts should be <= original (due to rounding down)
	require.True(t, result.Amount0.LessThanOrEqual(amt0))
	require.True(t, result.Amount1.LessThanOrEqual(amt1))
}

func TestAmountsForLiquidity_BelowRange(t *testing.T) {
	sqrtLower, _ := tickmath.TickToSqrtPriceX96(-1000)
	sqrtUpper, _ := tickmath.TickToSqrtPriceX96(1000)
	sqrtCurrent, _ := tickmath.TickToSqrtPriceX96(-2000)

	lq := big.NewInt(1000000000)
	result, err := tickmath.AmountsForLiquidity(sqrtLower, sqrtUpper, sqrtCurrent, lq)
	require.NoError(t, err)
	require.True(t, result.Amount0.IsPositive())
	require.True(t, result.Amount1.IsZero())
}

func TestAmountsForLiquidity_AboveRange(t *testing.T) {
	sqrtLower, _ := tickmath.TickToSqrtPriceX96(-1000)
	sqrtUpper, _ := tickmath.TickToSqrtPriceX96(1000)
	sqrtCurrent, _ := tickmath.TickToSqrtPriceX96(2000)

	lq := big.NewInt(1000000000)
	result, err := tickmath.AmountsForLiquidity(sqrtLower, sqrtUpper, sqrtCurrent, lq)
	require.NoError(t, err)
	require.True(t, result.Amount0.IsZero())
	require.True(t, result.Amount1.IsPositive())
}

func TestAmountsForLiquidity_InRange(t *testing.T) {
	sqrtLower, _ := tickmath.TickToSqrtPriceX96(-1000)
	sqrtUpper, _ := tickmath.TickToSqrtPriceX96(1000)
	sqrtCurrent, _ := tickmath.TickToSqrtPriceX96(0)

	lq := big.NewInt(1000000000)
	result, err := tickmath.AmountsForLiquidity(sqrtLower, sqrtUpper, sqrtCurrent, lq)
	require.NoError(t, err)
	// In range: both amounts should be positive
	require.True(t, result.Amount0.IsPositive())
	require.True(t, result.Amount1.IsPositive())
}
