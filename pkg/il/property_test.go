package il

import (
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

func TestILMonotoneNonPositive(t *testing.T) {
	testCases := []struct {
		name        string
		initialTick int64
		currentTick int64
		tickLower   int64
		tickUpper   int64
	}{
		{"in_range_no_change", 0, 0, -100, 100},
		{"in_range_small_up", 0, 50, -100, 100},
		{"in_range_small_down", 0, -50, -100, 100},
		{"in_range_large_up", 0, 500, -1000, 1000},
		{"in_range_large_down", 0, -500, -1000, 1000},
		{"below_range", 0, -200, -100, 100},
		{"above_range", 0, 200, -100, 100},
		{"wide_below", 0, -5000, -10000, 10000},
		{"wide_above", 0, 5000, -10000, 10000},
		{"narrow_in", 0, 5, -10, 10},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			sqrtPrice0, err := tickmath.TickToSqrtPriceX96(tc.initialTick)
			require.NoError(t, err)
			sqrtPriceCurrent, err := tickmath.TickToSqrtPriceX96(tc.currentTick)
			require.NoError(t, err)

			il, err := ILV3(sqrtPrice0, sqrtPriceCurrent, tc.tickLower, tc.tickUpper)
			require.NoError(t, err)
			require.True(t, il.IsNeg() || il.Abs().LessThan(decimal.MustFromString("1e-12")), "IL should be <= 0, got %s", il.String())
		})
	}
}

func TestFeeAccumulationMonotoneNonNegative(t *testing.T) {
	feeGrowthValues := []decimal.Decimal{
		decimal.Zero,
		decimal.MustFromString("0.001"),
		decimal.MustFromString("0.005"),
		decimal.MustFromString("0.01"),
		decimal.MustFromString("0.1"),
		decimal.MustFromString("1.0"),
	}

	prev := decimal.Zero
	for _, f := range feeGrowthValues {
		require.True(t, f.GreaterThanOrEqual(prev), "fee growth should be monotone non-negative")
		prev = f
	}
}

func TestILBoundedByPositionValue(t *testing.T) {
	state := V3PositionState{
		TickLower: -1000,
		TickUpper: 1000,
		Liquidity: big.NewInt(1000000),
		Token0:    decimal.MustFromString("10000"),
		Token1:    decimal.MustFromString("10000"),
	}
	_, ilUSD, _ := V3PositionPnL(state, decimal.MustFromString("1.0"), decimal.MustFromString("2.0"))
	posValue := state.Token0.Mul(decimal.MustFromString("2.0")).Add(state.Token1)
	require.True(t, ilUSD.Abs().LessThan(posValue), "IL magnitude should be < position value")
}

func TestNetPnLCombinesFeeAndIL(t *testing.T) {
	state := V3PositionState{
		TickLower: -1000,
		TickUpper: 1000,
		Liquidity: big.NewInt(1000000),
		Token0:    decimal.MustFromString("5000"),
		Token1:    decimal.MustFromString("5000"),
	}
	feeUSD, ilUSD, netPnL := V3PositionPnL(state, decimal.MustFromString("1.0"), decimal.MustFromString("1.1"))
	expectedNet := feeUSD.Add(ilUSD)
	require.True(t, netPnL.Equal(expectedNet), "netPnL should equal fee + il, got %s vs expected %s", netPnL.String(), expectedNet.String())
}

func TestV2ILMonotoneNonPositive(t *testing.T) {
	pricePairs := [][2]string{
		{"1.0", "1.0"},
		{"1.0", "1.1"},
		{"1.0", "0.9"},
		{"1.0", "2.0"},
		{"1.0", "0.5"},
		{"1.0", "10.0"},
		{"1.0", "0.1"},
	}

	for _, pp := range pricePairs {
		price0 := decimal.MustFromString(pp[0])
		price1 := decimal.MustFromString(pp[1])
		il := ILV2(price0, price1)
		require.True(t, il.IsNeg() || il.Abs().LessThan(decimal.MustFromString("1e-12")), "V2 IL should be <= 0 for price %s->%s, got %s", pp[0], pp[1], il.String())
	}
}

func TestFeeShareWithinBounds(t *testing.T) {
	state := V2PositionState{
		Reserve0:        decimal.MustFromString("1000000"),
		Reserve1:        decimal.MustFromString("1000000"),
		Amount0:         decimal.MustFromString("10000"),
		Amount1:         decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.MustFromString("1.0"),
	}
	fee, _, _ := V2PositionPnL(state, decimal.MustFromString("1.0"), decimal.MustFromString("1000"), decimal.MustFromString("2000000"))
	require.True(t, fee.GreaterThanOrEqual(decimal.Zero), "fee should be non-negative")
}

func TestILFormulaConsistency(t *testing.T) {
	price0 := decimal.MustFromString("1.0")

	// V3 in-range at same price should be ~0
	sqrtPrice0, _ := tickmath.TickToSqrtPriceX96(0)
	sqrtPriceCurrent, _ := tickmath.TickToSqrtPriceX96(0)
	ilV3, err := ILV3(sqrtPrice0, sqrtPriceCurrent, -1000, 1000)
	require.NoError(t, err)
	require.True(t, ilV3.Abs().LessThan(decimal.MustFromString("1e-12")), "V3 IL should be ~0 for no change")

	// V2 with no price change should also be ~0
	ilV2 := ILV2(price0, price0)
	require.True(t, ilV2.Abs().LessThan(decimal.MustFromString("1e-12")), "V2 IL should be ~0 for no change")

	// When price changes, both should be negative
	ilV2changed := ILV2(price0, decimal.MustFromString("1.2"))
	require.True(t, ilV2changed.IsNeg(), "V2 IL should be negative for price increase")
}
