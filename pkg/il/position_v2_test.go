package il

import (
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/stretchr/testify/require"
)

func TestV2PositionPnL_PriceUnchanged(t *testing.T) {
	// Test case 1: Price unchanged -> IL=0, fee based on proportion
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("1000000"),
		Reserve1:       decimal.MustFromString("1000000"),
		Amount0:        decimal.MustFromString("10000"),
		Amount1:        decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.FromInt(1000),
	}
	currentPrice := decimal.FromInt(1000)  // same as initial
	feeVolume := decimal.MustFromString("10000") // 24h volume
	tvl := decimal.MustFromString("2000000") // pool TVL

	feeUSD, ilUSD, netPnL := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// IL should be ~0 (price unchanged)
	require.True(t, ilUSD.Abs().LessThan(decimal.FromInt(1)),
		"IL should be ~0 when price unchanged, got %s", ilUSD.String())

	// Fee should be proportional to liquidity share
	// position is 1% of pool (10000/1000000), so fee should be ~100
	positionShare := decimal.MustFromString("0.01")
	expectedFee := decimal.MustFromString("100")
	feeDiff := feeUSD.Sub(expectedFee).Abs()
	require.True(t, feeDiff.LessThan(decimal.MustFromString("1")),
		"Fee should be ~100 (1% of 10000 volume), got %s", feeUSD.String())

	// Net PnL = fee + IL = fee + 0 = fee
	t.Logf("Test 1: Price unchanged - fee=%s, il=%s, net=%s", feeUSD.String(), ilUSD.String(), netPnL.String())
	_ = positionShare
}

func TestV2PositionPnL_PriceDropped(t *testing.T) {
	// Test case 2: Price dropped -> IL<0, fee partially offsets
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("1000000"),
		Reserve1:       decimal.MustFromString("1000000"),
		Amount0:        decimal.MustFromString("10000"),
		Amount1:        decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.FromInt(1000), // opened at 1000
	}
	currentPrice := decimal.MustFromString("500") // price dropped 50%
	feeVolume := decimal.MustFromString("10000")
	tvl := decimal.MustFromString("1500000") // pool value dropped too

	feeUSD, ilUSD, netPnL := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// IL should be negative (loss)
	require.True(t, ilUSD.IsNeg(), "IL should be negative when price dropped, got %s", ilUSD.String())
	t.Logf("Test 2: Price dropped 50%% - fee=%s, il=%s (negative=loss), net=%s",
		feeUSD.String(), ilUSD.String(), netPnL.String())

	// Net should be fee + IL (IL is negative, so net < fee)
	require.True(t, netPnL.LessThan(feeUSD),
		"Net should be less than fee since IL is negative")
}

func TestV2PositionPnL_FeeToTVLRatio(t *testing.T) {
	// Test case 3: fee/tvl ratio is correct
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("1000000"),
		Reserve1:       decimal.MustFromString("1000000"),
		Amount0:        decimal.MustFromString("100000"), // 10% of pool
		Amount1:        decimal.MustFromString("100000"),
		InitialPrice0USD: decimal.FromInt(1000),
	}
	currentPrice := decimal.FromInt(1000)
	feeVolume := decimal.MustFromString("30000") // 30k daily volume
	tvl := decimal.MustFromString("2000000") // 2M TVL

	feeUSD, _, _ := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// Position is 10% of pool, so fee should be ~10% of volume = 3000
	expectedFee := decimal.MustFromString("3000")
	feeDiff := feeUSD.Sub(expectedFee).Abs()
	require.True(t, feeDiff.LessThan(decimal.MustFromString("1")),
		"Fee should be ~3000 (10%% of 30k), got %s", feeUSD.String())

	// Verify fee/tvl ratio calculation is correct
	// 30k / 2M = 0.015 -> 1.5% daily fee yield
	feeRatio, _ := feeVolume.Div(tvl)
	require.True(t, feeRatio.LessThan(decimal.MustFromString("0.02")),
		"fee/tvl ratio should be < 2%%, got %s", feeRatio.String())
}

func TestV2PositionPnL_EmptyPosition(t *testing.T) {
	// Test case 4: Empty position (no amounts)
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("1000000"),
		Reserve1:       decimal.MustFromString("1000000"),
		Amount0:        decimal.Zero,
		Amount1:        decimal.Zero,
		InitialPrice0USD: decimal.FromInt(1000),
	}
	currentPrice := decimal.MustFromString("500")
	feeVolume := decimal.MustFromString("10000")
	tvl := decimal.MustFromString("1500000")

	feeUSD, ilUSD, netPnL := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// All should be zero
	require.True(t, feeUSD.IsZero() || feeUSD.Abs().LessThan(decimal.MustFromString("0.01")),
		"Fee should be ~0 for empty position")
	require.True(t, ilUSD.IsZero() || ilUSD.Abs().LessThan(decimal.MustFromString("0.01")),
		"IL should be ~0 for empty position")
	require.True(t, netPnL.IsZero() || netPnL.Abs().LessThan(decimal.MustFromString("0.01")),
		"Net should be ~0 for empty position")
}

func TestV2PositionPnL_ILCalculation(t *testing.T) {
	// Test IL calculation directly matches ILV2
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("1000000"),
		Reserve1:       decimal.MustFromString("1000000"),
		Amount0:        decimal.MustFromString("10000"),
		Amount1:        decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.FromInt(1000),
	}
	// price drops to 500 (50%)
	currentPrice := decimal.MustFromString("500")
	feeVolume := decimal.Zero // no fees for cleaner IL test
	tvl := decimal.MustFromString("1500000")

	_, ilUSD, _ := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// LP value at current price: 10000*500 + 10000 = 5,010,000
	lpValue := decimal.MustFromString("5010000")

	// ILV2(1000, 500) should give approximately -0.134
	expectedILPct := ILV2(decimal.FromInt(1000), decimal.MustFromString("500"))

	// Expected IL in USD = lpValue * ilPct
	expectedIL := lpValue.Mul(expectedILPct)

	// Allow some tolerance due to rounding
	ilDiff := ilUSD.Sub(expectedIL).Abs()
	t.Logf("IL: got %s, expected %s (IL%%=%s)", ilUSD.String(), expectedIL.String(), expectedILPct.String())

	// Should be within 1% of expected
	tolerance := expectedIL.Abs().Mul(decimal.MustFromString("0.01"))
	require.True(t, ilDiff.LessThan(tolerance.Add(decimal.MustFromString("1"))),
		"IL should match ILV2 calculation, diff=%s", ilDiff.String())
}

func TestV2PositionPnL_NetPnLCalculation(t *testing.T) {
	// Test that net = fee - |IL|
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("1000000"),
		Reserve1:       decimal.MustFromString("1000000"),
		Amount0:        decimal.MustFromString("10000"),
		Amount1:        decimal.MustFromString("10000"),
		InitialPrice0USD: decimal.FromInt(1000),
	}
	currentPrice := decimal.MustFromString("800") // 20% drop
	feeVolume := decimal.MustFromString("5000") // 5k daily volume
	tvl := decimal.MustFromString("1800000")

	feeUSD, ilUSD, netPnL := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// net = fee + il (il is negative)
	expectedNet := feeUSD.Add(ilUSD)

	netDiff := netPnL.Sub(expectedNet).Abs()
	require.True(t, netDiff.LessThan(decimal.MustFromString("0.01")),
		"Net PnL should be fee + il, got diff=%s", netDiff.String())

	t.Logf("Test: net = fee + il: %s = %s + %s", netPnL.String(), feeUSD.String(), ilUSD.String())
}

func TestV2PositionPnL_FeeShareCalculation(t *testing.T) {
	// Test that fee share = position_value / pool_value
	state := V2PositionState{
		Reserve0:       decimal.MustFromString("500000"),
		Reserve1:       decimal.MustFromString("500000"),
		Amount0:        decimal.MustFromString("50000"), // 10% of pool
		Amount1:        decimal.MustFromString("50000"),
		InitialPrice0USD: decimal.FromInt(1000),
	}
	currentPrice := decimal.FromInt(1000)
	feeVolume := decimal.FromInt(10000) // 10k daily
	tvl := decimal.MustFromString("1000000") // 1M pool

	feeUSD, _, _ := V2PositionPnL(state, currentPrice, feeVolume, tvl)

	// 10% of pool * 10k volume = 1k fee
	expectedFee := decimal.FromInt(1000)
	feeDiff := feeUSD.Sub(expectedFee).Abs()
	require.True(t, feeDiff.LessThan(decimal.MustFromString("0.1")),
		"Fee should be ~1000 (10%% share of 10k volume), got %s", feeUSD.String())
}