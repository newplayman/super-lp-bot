package il

import (
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

func TestNetPnL_V2(t *testing.T) {
	state := V2PositionState{
		Reserve0:        decimal.MustFromString("1000000"),
		Reserve1:        decimal.MustFromString("1000000"),
		Amount0:         decimal.MustFromString("10000"),
		Amount1:         decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.MustFromString("1.0"),
	}
	currentPrice := decimal.MustFromString("1.1") // 10% price increase
	feeVolume := decimal.MustFromString("1000")
	tvl := decimal.MustFromString("2000000")

	feeUSD, ilUSD, netPnL, err := NetPnL(true, state, state.InitialPrice0USD, currentPrice, feeVolume, tvl)
	require.NoError(t, err)

	// Fee should be positive (some share of fee volume)
	require.True(t, feeUSD.GreaterThan(decimal.Zero), "feeUSD should be positive")

	// IL should be negative (price moved, LP loses IL)
	require.True(t, ilUSD.IsNeg(), "ilUSD should be negative (loss)")

	// Net = fee + il (il is negative, so net < fee)
	require.True(t, netPnL.LessThan(feeUSD), "netPnL should be less than feeUSD due to IL")

	// IL formula: IL = 2*sqrt(1.1)/2.1 - 1 ≈ -0.048% for 10% move
	// Position value = 10000*1.1 + 10000 = 21000
	// IL ≈ 21000 * (-0.00048) ≈ -10
	ilPct := ILV2(state.InitialPrice0USD, currentPrice)
	expectedIL := decimal.FromInt(21000).Mul(ilPct)
	ilDiff := ilUSD.Sub(expectedIL).Abs()
	require.True(t, ilDiff.LessThan(decimal.MustFromString("1")), "IL should match expected value")
}

func TestNetPnL_V3(t *testing.T) {
	state := V3PositionState{
		TickLower: -1000,
		TickUpper: 1000,
		Liquidity: big.NewInt(1000000),
		Token0:    decimal.MustFromString("5000"),
		Token1:    decimal.MustFromString("5000"),
	}
	currentPrice := decimal.MustFromString("1.05")
	initialPrice := decimal.MustFromString("1.0")

	feeUSD, ilUSD, netPnL, err := NetPnL(false, state, initialPrice, currentPrice, decimal.Zero, decimal.Zero)
	require.NoError(t, err)

	// For V3, feeUSD is position value (token0 * price + token1)
	// IL should be small negative for small price move in wide range
	_ = feeUSD
	_ = ilUSD
	_ = netPnL
}

func TestNetPnLForTokenAmounts_V2(t *testing.T) {
	positionValue := decimal.MustFromString("10000")
	initialPrice := decimal.MustFromString("1.0")
	currentPrice := decimal.MustFromString("0.9") // 10% price drop

	feeUSD, ilUSD, netPnL, err := NetPnLForTokenAmounts(
		true, // V2
		positionValue, initialPrice, currentPrice,
		nil, nil, 0, 0, // V3 params ignored for V2
		decimal.Zero, decimal.Zero, decimal.Zero,
	)
	require.NoError(t, err)

	// Fee should be zero for this simple calculation
	require.True(t, feeUSD.IsZero(), "feeUSD should be zero for simple V2 calc")

	// IL should be negative (price dropped)
	require.True(t, ilUSD.IsNeg(), "ilUSD should be negative for price drop")

	// Net = il (negative)
	require.True(t, netPnL.IsNeg(), "netPnL should be negative")
}

func TestNetPnLForTokenAmounts_V3(t *testing.T) {
	sqrtPrice0, _ := tickmath.TickToSqrtPriceX96(0)
	sqrtPriceCurrent, _ := tickmath.TickToSqrtPriceX96(100) // price moved up

	positionValue := decimal.MustFromString("10000")
	initialPrice := decimal.MustFromString("1.0")
	currentPrice := decimal.MustFromString("1.0")

	feeGrowth := decimal.MustFromString("0.01")
	feeGrowthLast := decimal.Zero
	liquidity := decimal.MustFromString("1000")

	feeUSD, ilUSD, netPnL, err := NetPnLForTokenAmounts(
		false, // V3
		positionValue, initialPrice, currentPrice,
		sqrtPrice0, sqrtPriceCurrent,
		-1000, 1000, // tick range
		feeGrowth, feeGrowthLast, liquidity,
	)
	require.NoError(t, err)

	// Fee = (0.01 - 0) * 1000 = 10
	expectedFee := decimal.MustFromString("0.01").Mul(liquidity)
	require.True(t, feeUSD.Equal(expectedFee), "feeUSD should be %s, got %s", expectedFee.String(), feeUSD.String())

	// IL should be negative (price moved from initial sqrtPrice0)
	require.True(t, ilUSD.IsNeg(), "ilUSD should be negative for price move")

	// Net = fee + il
	_ = netPnL
}

func TestNetPnL_NetCanBeNegative(t *testing.T) {
	// Scenario: large price move causes IL > fees
	state := V2PositionState{
		Reserve0:        decimal.MustFromString("1000000"),
		Reserve1:        decimal.MustFromString("1000000"),
		Amount0:         decimal.MustFromString("100"),
		Amount1:         decimal.MustFromString("1000000"), // mostly USDC
		InitialPrice0USD: decimal.MustFromString("1.0"),
	}
	// 2x price increase = ~-5.7% IL
	currentPrice := decimal.MustFromString("2.0")
	feeVolume := decimal.MustFromString("1") // tiny fee volume
	tvl := decimal.MustFromString("2000000")

	_, _, netPnL, err := NetPnL(true, state, state.InitialPrice0USD, currentPrice, feeVolume, tvl)
	require.NoError(t, err)

	// IL for 2x move: ~-5.7% of position value
	// Position value ≈ 100*2 + 1000000 = 1000200
	// IL ≈ -57000
	// Net should be negative (IL > fees)
	require.True(t, netPnL.IsNeg(), "netPnL should be negative when IL exceeds fees")
}

func TestNetPnL_FeeMonotonicNonNegative(t *testing.T) {
	// Verify fee income is always non-negative
	state := V2PositionState{
		Reserve0:        decimal.MustFromString("1000000"),
		Reserve1:        decimal.MustFromString("1000000"),
		Amount0:         decimal.MustFromString("10000"),
		Amount1:         decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.MustFromString("1.0"),
	}
	currentPrice := decimal.MustFromString("1.0")
	feeVolumes := []decimal.Decimal{
		decimal.Zero,
		decimal.MustFromString("1"),
		decimal.MustFromString("1000"),
		decimal.MustFromString("100000"),
	}
	tvl := decimal.MustFromString("2000000")

	for _, fv := range feeVolumes {
		feeUSD, _, _, err := NetPnL(true, state, state.InitialPrice0USD, currentPrice, fv, tvl)
		require.NoError(t, err)
		require.True(t, feeUSD.GreaterThanOrEqual(decimal.Zero), "feeUSD should be non-negative, got %s", feeUSD.String())
	}
}