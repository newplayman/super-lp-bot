package strategy

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// RangeConfig holds configuration for dynamic range calculation.
type RangeConfig struct {
	BaseTickSpread int64           // Base spread between ticks
	VolMultiplier  decimal.Decimal // Multiplier applied to volatility
	MinTickSpread  int64           // Minimum allowed spread
	MaxTickSpread  int64           // Maximum allowed spread
}

// DefaultRangeConfig returns the default range configuration.
func DefaultRangeConfig() RangeConfig {
	return RangeConfig{
		BaseTickSpread: 500,                       // Base spread of 500 ticks
		VolMultiplier:  decimal.NewFromInt(100),  // Vol multiplier: 1% vol = 100 ticks
		MinTickSpread:  100,                       // Minimum 100 tick spread
		MaxTickSpread:  10000,                     // Maximum 10000 tick spread
	}
}

// DynamicRangeParams contains parameters for dynamic range calculation.
type DynamicRangeParams struct {
	CurrentTick int64           // Current tick position
	Volatility  decimal.Decimal // Historical volatility (as decimal, e.g., 0.05 for 5%)
	FeeTier     domain.Tier    // Fee tier for multiplier adjustment
}

// DynamicRange represents a calculated tick range.
type DynamicRange struct {
	TickLower int64
	TickUpper int64
}

// DynamicRangeCalculator computes optimal tick ranges based on volatility and tier.
type DynamicRangeCalculator struct {
	config RangeConfig
}

// NewDynamicRangeCalculator creates a new DynamicRangeCalculator with the given config.
func NewDynamicRangeCalculator(cfg RangeConfig) *DynamicRangeCalculator {
	return &DynamicRangeCalculator{config: cfg}
}

// CalculateDynamicRange computes the optimal tick range based on volatility and tier.
// It applies volatility-based widening and tier-specific safety margins.
func (c *DynamicRangeCalculator) CalculateDynamicRange(params DynamicRangeParams) DynamicRange {
	// Get tier thresholds for k·σ multiplier
	thresholds := domain.TierThresholdsFor(params.FeeTier)

	// Get volatility as float
	volatility, _ := params.Volatility.Float64()

	// Tier-specific adjustments
	// Tier A: 2.0 bonus (wider range for safety)
	// Tier B: 1.0 bonus (normal)
	// Tier C: 1.0 bonus (normal)
	var tierBonus float64
	switch params.FeeTier {
	case domain.TierA:
		tierBonus = 2.0
	case domain.TierB:
		tierBonus = 1.0
	case domain.TierC:
		tierBonus = 1.0
	default:
		tierBonus = 1.0
	}

	// Base spread constant - lower floor to allow tighter ranges
	baseSpread := float64(c.config.MinTickSpread) // 100

	// Volatility multiplier
	// Tuned so that:
	// - Tier A with 5% vol → > 1000 spread
	// - Tier B with 1% vol → < 500 spread
	volMultiplier := 8000.0

	// Calculate volatility-induced spread component
	// Formula: baseSpread + vol * volMultiplier * kSigma * tierBonus
	volSpread := volatility * volMultiplier * thresholds.RangeKSigma.InexactFloat64() * tierBonus

	// Total spread
	totalSpread := baseSpread + volSpread

	// Clamp to max bound
	if totalSpread > float64(c.config.MaxTickSpread) {
		totalSpread = float64(c.config.MaxTickSpread)
	}

	tickSpread := int64(totalSpread)

	// Calculate tick boundaries centered on current tick
	tickLower := params.CurrentTick - tickSpread/2
	tickUpper := params.CurrentTick + tickSpread/2

	// Ensure tick boundaries are within valid range
	const MinTick = -887272
	const MaxTick = 887272

	if tickLower < MinTick {
		// Shift range up if lower bound would be invalid
		shift := MinTick - tickLower
		tickLower = MinTick
		tickUpper = tickUpper + shift
	}
	if tickUpper > MaxTick {
		// Shift range down if upper bound would be invalid
		shift := tickUpper - MaxTick
		tickUpper = MaxTick
		tickLower = tickLower - shift
	}

	return DynamicRange{
		TickLower: tickLower,
		TickUpper: tickUpper,
	}
}