package strategy

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// RebalanceConfig holds configuration for rebalance decisions.
type RebalanceConfig struct {
	// BreachTolerancePct is the maximum allowed breach percentage before triggering rebalance.
	// Default is 0.03 (3%).
	BreachTolerancePct float64
}

// DefaultRebalanceConfig returns the default rebalance configuration.
func DefaultRebalanceConfig() RebalanceConfig {
	return RebalanceConfig{
		BreachTolerancePct: 0.03, // 3% default tolerance
	}
}

// RebalanceDecision represents the decision to rebalance a position.
type RebalanceDecision struct {
	PositionID    string
	Reason        domain.RebalanceReason
	NewRange      domain.TickRange
	EstimatedCost decimal.Decimal
}

// RebalanceTrigger evaluates position breaches and determines if rebalancing is needed.
type RebalanceTrigger struct {
	config   RebalanceConfig
	executor ExecutionPort
}

// ExecutionPort defines the interface for executing rebalance operations.
type ExecutionPort interface {
	// ExecuteRebalance executes a rebalance transaction.
	// (Currently not used in trigger, but available for future integration)
}

// NewRebalanceTrigger creates a new RebalanceTrigger with default configuration.
func NewRebalanceTrigger(executor ExecutionPort) *RebalanceTrigger {
	return &RebalanceTrigger{
		config:   DefaultRebalanceConfig(),
		executor: executor,
	}
}

// NewRebalanceTriggerWithConfig creates a new RebalanceTrigger with custom configuration.
func NewRebalanceTriggerWithConfig(config RebalanceConfig, executor ExecutionPort) *RebalanceTrigger {
	return &RebalanceTrigger{
		config:   config,
		executor: executor,
	}
}

// ShouldRebalance evaluates whether a position breach warrants rebalancing.
func (r *RebalanceTrigger) ShouldRebalance(ctx context.Context, breach domain.PositionBreach) (bool, *RebalanceDecision) {
	// Calculate breach percentage
	breachPct := r.calculateBreachPercentage(breach)

	// If breach is within tolerance, no rebalance needed
	if breachPct <= r.config.BreachTolerancePct {
		return false, nil
	}

	// Calculate new range centered on current price
	newRange := r.calculateNewRange(breach)

	// Estimate rebalance cost (simplified - would use simulator in real implementation)
	estimatedCost := r.estimateRebalanceCost(breach)

	decision := &RebalanceDecision{
		PositionID:    breach.PositionID,
		Reason:        domain.RebalanceReasonRangeBreach,
		NewRange:      newRange,
		EstimatedCost: estimatedCost,
	}

	return true, decision
}

// calculateBreachPercentage calculates how far the price has breached the range.
func (r *RebalanceTrigger) calculateBreachPercentage(breach domain.PositionBreach) float64 {
	switch breach.Type {
	case domain.BreachTypeRangeBelow:
		// Price went below lower bound
		// Calculate how far below: (RangeLower - Price) / RangeLower
		diff := breach.RangeLower.Sub(breach.PriceAtBreach)
		// For below breach, we measure against the lower bound
		if breach.RangeLower.GreaterThan(decimal.Zero) {
			pct := diff.Div(breach.RangeLower)
			pctFloat, _ := pct.Float64()
			return pctFloat
		}
	case domain.BreachTypeRangeAbove:
		// Price went above upper bound
		// Calculate how far above: (Price - RangeUpper) / RangeUpper
		diff := breach.PriceAtBreach.Sub(breach.RangeUpper)
		if breach.RangeUpper.GreaterThan(decimal.Zero) {
			pct := diff.Div(breach.RangeUpper)
			pctFloat, _ := pct.Float64()
			return pctFloat
		}
	}

	return 0.0
}

// calculateNewRange calculates a new tick range centered on the current price.
func (r *RebalanceTrigger) calculateNewRange(breach domain.PositionBreach) domain.TickRange {
	// Get the original range width
	originalWidth := breach.RangeUpper.Sub(breach.RangeLower)
	width, _ := originalWidth.Float64()
	tickWidth := int64(width)

	// For simplicity, use a default tick conversion
	// In real implementation, would convert price to tick
	currentTick := int64(200000) // Placeholder

	// Calculate new range centered on current tick
	tickLower := currentTick - tickWidth/2
	tickUpper := currentTick + tickWidth/2

	// Ensure valid tick boundaries
	const MinTick = -887272
	const MaxTick = 887272

	if tickLower < MinTick {
		tickLower = MinTick
	}
	if tickUpper > MaxTick {
		tickUpper = MaxTick
	}

	return domain.TickRange{
		TickLower: tickLower,
		TickUpper: tickUpper,
	}
}

// estimateRebalanceCost provides a rough estimate of rebalance gas costs.
func (r *RebalanceTrigger) estimateRebalanceCost(breach domain.PositionBreach) decimal.Decimal {
	// Simplified cost estimation
	// Real implementation would use simulation results
	// Average rebalance cost: ~0.005 ETH in gas
	return decimal.NewFromFloat(0.005)
}