package il

import (
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

func TestILV3_NoChangeInRange(t *testing.T) {
	tickLower := int64(-1000)
	tickUpper := int64(1000)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice0, tickLower, tickUpper)
	require.NoError(t, err)

	threshold := decimal.MustFromString("0.0001")
	require.True(t, il.Abs().LessThan(threshold))
}

func TestILV3_PriceBelowRange(t *testing.T) {
	tickLower := int64(-100)
	tickUpper := int64(100)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(-200)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, il.IsNeg(), "IL should be negative (loss)")
	require.True(t, il.Abs().GreaterThan(decimal.Zero), "IL magnitude should be positive")
}

func TestILV3_PriceAboveRange(t *testing.T) {
	tickLower := int64(-100)
	tickUpper := int64(100)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(200)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, il.IsNeg(), "IL should be negative (loss)")
	require.True(t, il.Abs().GreaterThan(decimal.Zero), "IL magnitude should be positive")
}

func TestILV3_InRange(t *testing.T) {
	tickLower := int64(-100)
	tickUpper := int64(100)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(50)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, il.IsNeg(), "IL should be negative (loss)")
}

func TestILV3_ILBounded(t *testing.T) {
	tickLower := int64(-500)
	tickUpper := int64(500)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	testPrices := []int64{-1000, -500, -100, 0, 100, 500, 1000}
	for _, tick := range testPrices {
		sqrtPrice1, err := tickmath.TickToSqrtPriceX96(tick)
		require.NoError(t, err)

		il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
		require.NoError(t, err, "IL should compute without error at tick %d", tick)

		// Allow tiny floating-point epsilon (~1e-10) for rounding errors
		epsilon := decimal.MustFromString("1e-10")
		absIL := il.Abs()
		absLT := absIL.LessThan(epsilon)
		require.True(t, il.IsNeg() || absLT, "IL should be <= 0 (or negligible), got %s at tick %d", il.String(), tick)
	}
}

func TestILV3_WideRange(t *testing.T) {
	tickLower := int64(-10000)
	tickUpper := int64(10000)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(1000)
	require.NoError(t, err)

	ilV3, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, ilV3.IsNeg(), "Wide range IL should still be negative")
}

func TestILV3_NarrowRange(t *testing.T) {
	tickLower := int64(-10)
	tickUpper := int64(10)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(100)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, il.IsNeg(), "Narrow range IL should be negative")
}

func TestILV3_InvalidTick(t *testing.T) {
	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(100)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, 100, -100)
	require.NoError(t, err)
	_ = il
}

func TestILV3_SymmetricRange(t *testing.T) {
	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	ranges := [][2]int64{
		{-10, 10},
		{-100, 100},
		{-1000, 1000},
	}

	for _, r := range ranges {
		il, err := ILV3(sqrtPrice0, sqrtPrice0, r[0], r[1])
		require.NoError(t, err)
		threshold := decimal.MustFromString("0.0001")
		require.True(t, il.Abs().LessThan(threshold),
			"IL should be ~0 when price = initial and in range")

		sqrtPrice1, err := tickmath.TickToSqrtPriceX96(r[1])
		require.NoError(t, err)
		il, err = ILV3(sqrtPrice0, sqrtPrice1, r[0], r[1])
		require.NoError(t, err)
		require.True(t, il.IsNeg(), "IL should be negative")
	}
}

func TestILV3_InitialPriceInRange(t *testing.T) {
	tickLower := int64(-100)
	tickUpper := int64(100)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(200)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, il.IsNeg())
}

func TestILV3_LargePriceMove(t *testing.T) {
	tickLower := int64(-1000)
	tickUpper := int64(1000)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPrice1, err := tickmath.TickToSqrtPriceX96(23000)
	require.NoError(t, err)

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)

	require.True(t, il.IsNeg())
	threshold := decimal.MustFromString("0.5")
	require.True(t, il.Abs().GreaterThan(threshold),
		"Large price move should result in significant IL, got %s", il.String())
}

func TestILV3_AtTickBoundary(t *testing.T) {
	tickLower := int64(-100)
	tickUpper := int64(100)

	sqrtPrice0, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)

	sqrtPriceLower, err := tickmath.TickToSqrtPriceX96(tickLower)
	require.NoError(t, err)
	ilLower, err := ILV3(sqrtPrice0, sqrtPriceLower, tickLower, tickUpper)
	require.NoError(t, err)
	thresholdLower := decimal.MustFromString("0.001")
	require.True(t, ilLower.IsNeg() || ilLower.Abs().LessThan(thresholdLower),
		"IL at lower bound should be ~0 or slightly negative")

	sqrtPriceUpper, err := tickmath.TickToSqrtPriceX96(tickUpper)
	require.NoError(t, err)
	ilUpper, err := ILV3(sqrtPrice0, sqrtPriceUpper, tickLower, tickUpper)
	require.NoError(t, err)
	require.True(t, ilUpper.IsNeg(), "IL at upper bound should be negative since price moved")
}

func TestILV3_BigIntInputs(t *testing.T) {
	tickLower := int64(-100)
	tickUpper := int64(100)

	sqrtPrice0 := new(big.Int).Mul(tickmath.Q96Big, big.NewInt(1))
	sqrtPrice1 := new(big.Int).Mul(tickmath.Q96Big, big.NewInt(2))

	il, err := ILV3(sqrtPrice0, sqrtPrice1, tickLower, tickUpper)
	require.NoError(t, err)
	threshold := decimal.MustFromString("0.001")
	require.True(t, il.IsNeg() || il.Abs().LessThan(threshold),
		"IL should be computed correctly with big.Int inputs")
}
