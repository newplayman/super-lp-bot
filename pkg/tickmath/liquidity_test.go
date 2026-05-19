package tickmath_test

import (
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

func TestLiquidityForAmounts_Simple(t *testing.T) {
	// If sqrtPriceCurrent is in range, liquidity > 0
	sqrtLower, _ := tickmath.TickToSqrtPriceX96(-1000)
	sqrtUpper, _ := tickmath.TickToSqrtPriceX96(1000)
	sqrtCurrent, _ := tickmath.TickToSqrtPriceX96(0)

	amt0 := decimal.MustFromString("1000000") // 1 USDC
	amt1 := decimal.MustFromString("1000000") // 1 USDC

	lq, err := tickmath.LiquidityForAmounts(sqrtLower, sqrtUpper, sqrtCurrent, amt0, amt1)
	require.NoError(t, err)
	require.True(t, lq.BitLen() > 0)
}

func TestLiquidityForAmounts_BelowRange(t *testing.T) {
	sqrtLower, _ := tickmath.TickToSqrtPriceX96(-1000)
	sqrtUpper, _ := tickmath.TickToSqrtPriceX96(1000)
	sqrtCurrent, _ := tickmath.TickToSqrtPriceX96(-2000) // below range

	amt0 := decimal.MustFromString("1000000")
	amt1 := decimal.Zero

	lq, err := tickmath.LiquidityForAmounts(sqrtLower, sqrtUpper, sqrtCurrent, amt0, amt1)
	require.NoError(t, err)
	require.True(t, lq.BitLen() > 0)
}
