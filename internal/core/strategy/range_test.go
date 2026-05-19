// Package strategy implements the position decision-making logic.
package strategy

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

// TestDynamicRangeCalculator_VolatilityAdjustment tests that high volatility leads to wider ranges
func TestDynamicRangeCalculator_VolatilityAdjustment(t *testing.T) {
	calc := NewDynamicRangeCalculator(DefaultRangeConfig())

	params := DynamicRangeParams{
		CurrentTick: 200000,
		Volatility:  decimal.NewFromFloat(0.05), // 5% daily vol
		FeeTier:     domain.TierA,
	}

	range_ := calc.CalculateDynamicRange(params)

	// High vol should result in wider range (tick spread > 1000)
	require.True(t, range_.TickUpper-range_.TickLower > 1000,
		"Expected range width > 1000 for high volatility, got %d",
		range_.TickUpper-range_.TickLower)
}

// TestDynamicRangeCalculator_LowVolatility tests that low volatility leads to tighter ranges
func TestDynamicRangeCalculator_LowVolatility(t *testing.T) {
	calc := NewDynamicRangeCalculator(DefaultRangeConfig())

	params := DynamicRangeParams{
		CurrentTick: 200000,
		Volatility:  decimal.NewFromFloat(0.01), // 1% daily vol
		FeeTier:     domain.TierB,
	}

	range_ := calc.CalculateDynamicRange(params)

	// Low vol should result in tighter range (tick spread < 500)
	require.True(t, range_.TickUpper-range_.TickLower < 500,
		"Expected range width < 500 for low volatility, got %d",
		range_.TickUpper-range_.TickLower)
}

// TestDynamicRangeCalculator_TierAdjustment tests that Tier A has wider ranges than Tier C
func TestDynamicRangeCalculator_TierAdjustment(t *testing.T) {
	calc := NewDynamicRangeCalculator(DefaultRangeConfig())

	baseParams := DynamicRangeParams{
		CurrentTick: 200000,
		Volatility: decimal.NewFromFloat(0.03),
	}

	tierA := calc.CalculateDynamicRange(DynamicRangeParams{
		CurrentTick: baseParams.CurrentTick,
		Volatility:  baseParams.Volatility,
		FeeTier:     domain.TierA,
	})

	tierC := calc.CalculateDynamicRange(DynamicRangeParams{
		CurrentTick: baseParams.CurrentTick,
		Volatility:  baseParams.Volatility,
		FeeTier:     domain.TierC,
	})

	// Tier A should have wider range than Tier C for safety
	require.True(t, tierA.TickUpper-tierA.TickLower > tierC.TickUpper-tierC.TickLower,
		"Expected Tier A range (%d) > Tier C range (%d)",
		tierA.TickUpper-tierA.TickLower,
		tierC.TickUpper-tierC.TickLower)
}

// TestDynamicRangeCalculator_TickBoundaries tests that tick boundaries are respected
func TestDynamicRangeCalculator_TickBoundaries(t *testing.T) {
	calc := NewDynamicRangeCalculator(DefaultRangeConfig())

	params := DynamicRangeParams{
		CurrentTick: 500000, // Very high tick
		Volatility: decimal.NewFromFloat(0.02),
		FeeTier:    domain.TierA,
	}

	range_ := calc.CalculateDynamicRange(params)

	// Check lower boundary
	require.GreaterOrEqual(t, range_.TickLower, int64(-887272),
		"TickLower should be >= -887272")
	// Check upper boundary
	require.LessOrEqual(t, range_.TickUpper, int64(887272),
		"TickUpper should be <= 887272")
}

// TestDynamicRangeCalculator_MinimumSpread tests that minimum spread is enforced
func TestDynamicRangeCalculator_MinimumSpread(t *testing.T) {
	calc := NewDynamicRangeCalculator(DefaultRangeConfig())

	params := DynamicRangeParams{
		CurrentTick: 100000,
		Volatility:  decimal.NewFromFloat(0.001), // Very low volatility
		FeeTier:     domain.TierA,
	}

	range_ := calc.CalculateDynamicRange(params)

	// Should still have minimum spread
	require.GreaterOrEqual(t, range_.TickUpper-range_.TickLower, calc.config.MinTickSpread,
		"Range should have minimum spread of %d, got %d",
		calc.config.MinTickSpread,
		range_.TickUpper-range_.TickLower)
}

// TestDynamicRangeCalculator_MaximumSpread tests that maximum spread is enforced
func TestDynamicRangeCalculator_MaximumSpread(t *testing.T) {
	calc := NewDynamicRangeCalculator(DefaultRangeConfig())

	params := DynamicRangeParams{
		CurrentTick: 100000,
		Volatility:  decimal.NewFromFloat(0.5), // Very high volatility
		FeeTier:     domain.TierA,
	}

	range_ := calc.CalculateDynamicRange(params)

	// Should not exceed maximum spread
	require.LessOrEqual(t, range_.TickUpper-range_.TickLower, calc.config.MaxTickSpread,
		"Range should have maximum spread of %d, got %d",
		calc.config.MaxTickSpread,
		range_.TickUpper-range_.TickLower)
}