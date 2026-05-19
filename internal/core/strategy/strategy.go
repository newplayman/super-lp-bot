// Package strategy implements the position decision-making logic.
package strategy

import (
	"context"
	"sort"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// defaultStrategy is the default implementation for Phase 1.
type defaultStrategy struct {
	filter PoolFilter
}

// New creates a new Strategy instance.
func New() Strategy {
	return &defaultStrategy{
		filter: DefaultPoolFilter(),
	}
}

// NewWithFilter creates a Strategy with custom filter criteria.
func NewWithFilter(filter PoolFilter) Strategy {
	return &defaultStrategy{filter: filter}
}

// EvaluatePool assesses whether a pool is a good candidate for positioning.
// Returns an Intent if the pool passes selection criteria, nil otherwise.
func (s *defaultStrategy) EvaluatePool(ctx context.Context, pool domain.Pool, score domain.Score) (*Intent, error) {
	// Compute total score
	totalScore := score.ComputeTotal()

	// Check score threshold
	if totalScore < 60 {
		return nil, nil // Score too low
	}

	// Assign tier from score
	tier := score.AssignTier()

	// Calculate range based on tier thresholds
	thresholds := domain.TierThresholdsFor(tier)
	kSigma, _ := thresholds.RangeKSigma.Float64()

	// Default tick from pool or 0
	tick := int64(0)
	volatility := 0.5

	// Calculate range width based on tier
	baseWidth := int64(500)
	switch tier {
	case domain.TierA:
		baseWidth = 800
	case domain.TierC:
		baseWidth = 300
	}

	rangeWidth := int64(float64(baseWidth) * kSigma * (volatility + 1))
	if rangeWidth < 100 {
		rangeWidth = 100
	}

	tickLower := tick - rangeWidth/2
	tickUpper := tick + rangeWidth/2

	// Ensure tick boundaries are valid
	if tickLower < -887272 {
		tickLower = -887272
	}
	if tickUpper > 887272 {
		tickUpper = 887272
	}

	// Create intent
	intent := &Intent{
		PoolID:  pool.ID,
		Chain:   pool.Chain,
		Tier:    tier,
		Range: RangeParams{
			TickLower:    tickLower,
			TickUpper:    tickUpper,
			AmountUSD:    thresholds.MaxPerPoolUSD,
			Concentrated: tier == domain.TierA || tier == domain.TierB,
		},
		TraceID: generateTraceID(),
		Reason:  generateReason(totalScore),
	}

	return intent, nil
}

// EvaluateRebalance checks if an existing position should be rebalanced.
func (s *defaultStrategy) EvaluateRebalance(ctx context.Context, pos domain.Position) (*Intent, error) {
	// Calculate current IL impact
	ilPct := calculateILFromPosition(pos)
	thresholds := domain.TierThresholdsFor(pos.Tier)

	// If IL exceeds threshold, suggest rebalance
	if ilPct.GreaterThan(thresholds.ILStopPct) {
		return &Intent{
			PoolID:  pos.PoolID,
			Chain:   pos.Chain,
			Tier:    pos.Tier,
			Range: RangeParams{
				TickLower:    pos.TickLower,
				TickUpper:    pos.TickUpper,
				AmountUSD:    pos.AmountUSD,
				Concentrated: true,
			},
			TraceID: generateTraceID(),
			Reason:  "IL breach: rebalance needed",
		}, nil
	}

	return nil, nil // No rebalance needed
}

// SelectCandidates returns the top N pools for potential positioning.
func (s *defaultStrategy) SelectCandidates(ctx context.Context, pools []domain.Pool, limit int) ([]domain.Pool, error) {
	if limit <= 0 {
		limit = 10
	}

	// Sort pools by ID for deterministic ordering (Phase 1 - no real scoring yet)
	sortedPools := make([]domain.Pool, len(pools))
	copy(sortedPools, pools)
	sort.Slice(sortedPools, func(i, j int) bool {
		return sortedPools[i].ID < sortedPools[j].ID
	})

	// Take top N
	if len(sortedPools) > limit {
		sortedPools = sortedPools[:limit]
	}

	return sortedPools, nil
}

// defaultRangeCalculator is the default implementation for Phase 1.
type defaultRangeCalculator struct{}

// NewRangeCalculator creates a new RangeCalculator.
func NewRangeCalculator() RangeCalculator {
	return &defaultRangeCalculator{}
}

// CalculateRange computes the tick range for a given pool and tier.
func (c *defaultRangeCalculator) CalculateRange(tick int64, volatility float64, tier domain.Tier) RangeParams {
	thresholds := domain.TierThresholdsFor(tier)
	kSigma, _ := thresholds.RangeKSigma.Float64()

	// Calculate range width based on volatility and k·σ
	rangeWidth := int64(volatility * kSigma * 100)
	if rangeWidth < 100 {
		rangeWidth = 100 // Minimum range width
	}

	// Apply tier-specific multipliers
	multiplier := float64(1)
	switch tier {
	case domain.TierA:
		multiplier = 1.5 // Wider range for Tier A
	case domain.TierB:
		multiplier = 1.2
	case domain.TierC:
		multiplier = 0.8 // Tighter range for Tier C
	}

	rangeWidth = int64(float64(rangeWidth) * multiplier)

	// Calculate tick boundaries
	tickLower := tick - rangeWidth/2
	tickUpper := tick + rangeWidth/2

	// Ensure tick boundaries are valid
	if tickLower < -887272 {
		tickLower = -887272
	}
	if tickUpper > 887272 {
		tickUpper = 887272
	}

	return RangeParams{
		TickLower:    tickLower,
		TickUpper:    tickUpper,
		AmountUSD:    thresholds.MaxPerPoolUSD,
		Concentrated: tier == domain.TierA || tier == domain.TierB,
	}
}

// AdjustRangeForRebalance adjusts an existing range based on current price.
func (c *defaultRangeCalculator) AdjustRangeForRebalance(currentTick, tickLower, tickUpper int64, breachPct float64) RangeParams {
	// Determine if rebalance is needed (breach > threshold)
	if breachPct > 0.2 { // 20% breach threshold
		// Calculate new range centered on current tick
		rangeWidth := tickUpper - tickLower
		newLower := currentTick - rangeWidth/2
		newUpper := currentTick + rangeWidth/2

		// Ensure valid bounds
		if newLower < -887272 {
			newLower = -887272
		}
		if newUpper > 887272 {
			newUpper = 887272
		}

		return RangeParams{
			TickLower:    newLower,
			TickUpper:    newUpper,
			Concentrated: true,
		}
	}

	// No adjustment needed
	return RangeParams{
		TickLower:    tickLower,
		TickUpper:    tickUpper,
		Concentrated: true,
	}
}

// CalculateRangeFromScore calculates range parameters from a score.
func CalculateRangeFromScore(score domain.Score, tier domain.Tier) RangeParams {
	thresholds := domain.TierThresholdsFor(tier)
	kSigma, _ := thresholds.RangeKSigma.Float64()

	// Default tick range width based on tier
	baseWidth := int64(500)
	switch tier {
	case domain.TierA:
		baseWidth = 800
	case domain.TierC:
		baseWidth = 300
	}

	volatility := 0.5
	rangeWidth := int64(float64(baseWidth) * kSigma * (volatility + 1))
	if rangeWidth < 100 {
		rangeWidth = 100
	}

	tick := int64(0)
	tickLower := tick - rangeWidth/2
	tickUpper := tick + rangeWidth/2

	return RangeParams{
		TickLower:    tickLower,
		TickUpper:    tickUpper,
		AmountUSD:    thresholds.MaxPerPoolUSD,
		Concentrated: tier == domain.TierA || tier == domain.TierB,
	}
}

// calculateILFromPosition calculates IL percentage from position.
func calculateILFromPosition(pos domain.Position) decimal.Decimal {
	// Simplified IL calculation
	// In real implementation, would compare current vs entry prices
	return decimal.Zero
}

// generateTraceID generates a unique trace ID.
func generateTraceID() string {
	return "trace-1" // Simplified for Phase 1
}

// generateReason generates a human-readable reason for the decision.
func generateReason(totalScore float64) string {
	if totalScore >= 80 {
		return "High score: excellent candidate"
	}
	if totalScore >= 60 {
		return "Good score: acceptable candidate"
	}
	return "Moderate score: marginal candidate"
}