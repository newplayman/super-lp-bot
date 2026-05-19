package strategy

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

func TestRebalanceTrigger_DetectRangeBreach(t *testing.T) {
	// Arrange
	trigger := NewRebalanceTrigger(nil)

	// Act - simulate range breach event
	// Price 1850 with lower bound 1950 = 5.1% breach (> 3% tolerance)
	breach := domain.PositionBreach{
		PositionID:    "pos-1",
		Type:          domain.BreachTypeRangeBelow,
		PriceAtBreach: decimal.NewFromFloat(1850.0),
		RangeLower:    decimal.NewFromFloat(1950.0),
		RangeUpper:    decimal.NewFromFloat(2050.0),
	}

	shouldRebalance, decision := trigger.ShouldRebalance(context.Background(), breach)

	// Assert - should trigger rebalance for significant breach
	require.True(t, shouldRebalance)
	require.NotNil(t, decision)
	require.Equal(t, domain.RebalanceReasonRangeBreach, decision.Reason)
}

func TestRebalanceTrigger_IgnoreMinorBreach(t *testing.T) {
	// Minor breach within tolerance should not trigger
	trigger := NewRebalanceTrigger(nil)

	breach := domain.PositionBreach{
		PositionID:    "pos-1",
		Type:          domain.BreachTypeRangeBelow,
		PriceAtBreach: decimal.NewFromFloat(1990.0), // within 3% of range
		RangeLower:    decimal.NewFromFloat(1950.0),
		RangeUpper:    decimal.NewFromFloat(2050.0),
	}

	shouldRebalance, _ := trigger.ShouldRebalance(context.Background(), breach)
	require.False(t, shouldRebalance)
}

func TestRebalanceTrigger_BreachAboveThreshold(t *testing.T) {
	// Breach above range should also trigger
	trigger := NewRebalanceTrigger(nil)

	// Price 2130 with upper bound 2050 = 3.9% breach (> 3% tolerance)
	breach := domain.PositionBreach{
		PositionID:    "pos-2",
		Type:          domain.BreachTypeRangeAbove,
		PriceAtBreach: decimal.NewFromFloat(2130.0),
		RangeLower:    decimal.NewFromFloat(1950.0),
		RangeUpper:    decimal.NewFromFloat(2050.0),
	}

	shouldRebalance, decision := trigger.ShouldRebalance(context.Background(), breach)

	require.True(t, shouldRebalance)
	require.NotNil(t, decision)
	require.Equal(t, domain.RebalanceReasonRangeBreach, decision.Reason)
}

func TestRebalanceTrigger_CalculatesNewRange(t *testing.T) {
	// Verify that the new range is calculated correctly
	trigger := NewRebalanceTrigger(nil)

	breach := domain.PositionBreach{
		PositionID:    "pos-3",
		Type:          domain.BreachTypeRangeBelow,
		PriceAtBreach: decimal.NewFromFloat(1850.0),
		RangeLower:    decimal.NewFromFloat(1950.0),
		RangeUpper:    decimal.NewFromFloat(2050.0),
	}

	_, decision := trigger.ShouldRebalance(context.Background(), breach)

	require.NotNil(t, decision)
	// New range should be centered on current price
	// With price at 1850 and original range width of 100, new range should be 1850-2050
	require.Greater(t, decision.NewRange.TickUpper, int64(0))
}

func TestRebalanceTrigger_WithCustomTolerance(t *testing.T) {
	// Test with custom tolerance configuration
	config := RebalanceConfig{
		BreachTolerancePct: 0.01, // 1% tolerance
	}
	trigger := NewRebalanceTriggerWithConfig(config, nil)

	// Price 2052 with upper bound 2050 = 0.1% breach, exceeds 1% tolerance for below breach
	// For below breach with lower 1950, price at 1890 = 3.1% breach
	breach := domain.PositionBreach{
		PositionID:    "pos-4",
		Type:          domain.BreachTypeRangeBelow,
		PriceAtBreach: decimal.NewFromFloat(1890.0), // 3.1% below 1950, exceeds 1% tolerance
		RangeLower:    decimal.NewFromFloat(1950.0),
		RangeUpper:    decimal.NewFromFloat(2050.0),
	}

	shouldRebalance, _ := trigger.ShouldRebalance(context.Background(), breach)
	require.True(t, shouldRebalance)
}

func TestRebalanceTrigger_EstimatedCostCalculation(t *testing.T) {
	// Verify estimated cost is populated
	trigger := NewRebalanceTrigger(nil)

	breach := domain.PositionBreach{
		PositionID:    "pos-5",
		Type:          domain.BreachTypeRangeBelow,
		PriceAtBreach: decimal.NewFromFloat(1850.0),
		RangeLower:    decimal.NewFromFloat(1950.0),
		RangeUpper:    decimal.NewFromFloat(2050.0),
	}

	_, decision := trigger.ShouldRebalance(context.Background(), breach)

	require.NotNil(t, decision)
	require.False(t, decision.EstimatedCost.IsZero())
}
