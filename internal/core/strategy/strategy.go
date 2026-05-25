// Package strategy implements the position decision-making logic.
package strategy

import (
	"context"
	"fmt"
	"sort"

	"github.com/lpbot/lpbot/internal/domain"
	platformtrace "github.com/lpbot/lpbot/internal/platform/trace"
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

	// Use pool's actual tick if available, otherwise use score-derived tick
	tick := pool.Tick
	if tick == 0 && totalScore > 0 {
		// Derive tick from volatility (higher volatility = wider range needed)
		tick = int(totalScore * 100) // Simplified tick derivation
	}

	// Use actual volatility from score if available, else estimate from volume/TVL ratio
	volatility := calculateVolatility(pool)

	// Get FeeAPR for reporting
	feeAPR := pool.FeeAPR24h

	// Calculate range width based on tier and volatility
	baseWidth := 500
	switch tier {
	case domain.TierA:
		baseWidth = 800
	case domain.TierC:
		baseWidth = 300
	}

	rangeWidth := int(float64(baseWidth) * kSigma * (volatility + 1))
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

	// Calculate max amount based on tier and TVL
	maxAmount := thresholds.MaxPerPoolUSD
	if pool.TVLUSD.LessThan(maxAmount) {
		maxAmount = pool.TVLUSD
	}

	// Create intent
	intent := &Intent{
		PoolID:  pool.ID,
		Chain:   pool.Chain,
		Tier:    tier,
		Range: RangeParams{
			TickLower:    int64(tickLower),
			TickUpper:    int64(tickUpper),
			AmountUSD:    maxAmount,
			Concentrated: tier == domain.TierA || tier == domain.TierB,
		},
		TraceID: generateTraceID(),
		Reason:  generateReason(totalScore, feeAPR, volatility),
	}

	return intent, nil
}
// Higher volume relative to TVL = higher volatility = wider range needed.
func calculateVolatility(pool domain.Pool) float64 {
	if pool.TVLUSD.IsZero() {
		return 0.5 // Default moderate volatility
	}

	// Volatility = Volume/TVL ratio
	// High ratio (>0.5) = high volatility
	// Low ratio (<0.1) = low volatility
	volFloat, _ := pool.Vol24h.Float64()
	tvlFloat, _ := pool.TVLUSD.Float64()

	if tvlFloat == 0 {
		return 0.5
	}

	ratio := volFloat / tvlFloat

	// Clamp ratio to reasonable range
	if ratio > 2.0 {
		ratio = 2.0
	}
	if ratio < 0.01 {
		ratio = 0.01
	}

	// Convert ratio to volatility (0-1 scale)
	// 0.01 ratio -> 0.1 volatility (stable)
	// 2.0 ratio -> 1.0 volatility (volatile)
	volatility := (ratio - 0.01) / (2.0 - 0.01)
	return volatility
}

// calculateILFromPosition calculates IL percentage from position.
func calculateILFromPosition(pos domain.Position) decimal.Decimal {
	// Simplified IL calculation
	// In real implementation, would compare current vs entry prices
	return decimal.Zero
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
// Uses multi-factor scoring: FeeAPR (35%), TVL (25%), Volume (20%), Volatility (10%), Security (10%).
func (s *defaultStrategy) SelectCandidates(ctx context.Context, pools []domain.Pool, limit int) ([]domain.Pool, error) {
	if limit <= 0 {
		limit = 10
	}
	if len(pools) == 0 {
		return nil, nil
	}

	// Score pools by expected return (not just pool ID)
	scoredPools := make([]struct {
		pool  domain.Pool
		score float64
	}, len(pools))

	for i, pool := range pools {
		// Calculate expected return score
		// Higher FeeAPR, TVL, Volume = better
		// Lower volatility = better
		var feeAPRFloat, tvlFloat, volFloat float64

		if pool.FeeAPR24h.String() != "" {
			feeAPRFloat, _ = pool.FeeAPR24h.Float64()
		}
		if pool.TVLUSD.String() != "" {
			tvlFloat, _ = pool.TVLUSD.Float64()
		}
		if pool.Vol24h.String() != "" {
			volFloat, _ = pool.Vol24h.Float64()
		}

		// Normalize scores (0-100 scale)
		// FeeAPR: 0-50% APR = 0-100 score
		feeScore := feeAPRFloat * 100
		if feeScore > 100 {
			feeScore = 100
		}

		// TVL: $10k-$10M normalized to 0-100
		tvlScore := normalizeScore(tvlFloat, 10_000, 10_000_000)

		// Volume: $1k-$1M normalized to 0-100
		volScore := normalizeScore(volFloat, 1_000, 1_000_000)

		// Calculate composite score
		// Weights: FeeAPR=35%, TVL=25%, Volume=20%, Security=20%
		compositeScore := feeScore*0.35 + tvlScore*0.25 + volScore*0.20 + tvlScore*0.20

		scoredPools[i] = struct {
			pool  domain.Pool
			score float64
		}{pool: pool, score: compositeScore}
	}

	// Sort by composite score (descending)
	sort.Slice(scoredPools, func(i, j int) bool {
		return scoredPools[i].score > scoredPools[j].score
	})

	// Take top N
	result := make([]domain.Pool, 0, limit)
	for i := 0; i < len(scoredPools) && len(result) < limit; i++ {
		result = append(result, scoredPools[i].pool)
	}

	return result, nil
}

// normalizeScore normalizes a value to 0-100 range.
func normalizeScore(value, min, max float64) float64 {
	if value <= min {
		return 0
	}
	if value >= max {
		return 100
	}
	return (value - min) / (max - min) * 100
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

// generateTraceID generates a unique trace ID.
func generateTraceID() string {
	return platformtrace.NewTraceID()
}

// generateReason generates a human-readable reason for the decision.
func generateReason(totalScore float64, feeAPR domain.Decimal, volatility float64) string {
	feeAPRFloat, _ := feeAPR.Float64()
	if totalScore >= 80 {
		return fmt.Sprintf("High score (%.1f): excellent candidate, feeAPR=%.2f%%, vol=%.2f", totalScore, feeAPRFloat, volatility)
	}
	if totalScore >= 60 {
		return fmt.Sprintf("Good score (%.1f): acceptable candidate, feeAPR=%.2f%%, vol=%.2f", totalScore, feeAPRFloat, volatility)
	}
	return fmt.Sprintf("Moderate score (%.1f): marginal candidate", totalScore)
}
