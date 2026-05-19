package risk

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// AllocationConfig holds per-tier allocation limits and max exposure.
type AllocationConfig struct {
	TierALimit  decimal.Decimal // max per pool for Tier A (default $1000)
	TierBLimit  decimal.Decimal // max per pool for Tier B (default $200)
	TierCLimit  decimal.Decimal // max per pool for Tier C (default $50)
	MaxExposure decimal.Decimal // max total exposure as fraction (default 0.30 = 30%)
}

// DefaultAllocationConfig returns sensible defaults per spec §8.5.
func DefaultAllocationConfig() AllocationConfig {
	return AllocationConfig{
		TierALimit:  decimal.NewFromInt(1000),
		TierBLimit:  decimal.NewFromInt(200),
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30), // 30%
	}
}

// AllocationManager enforces per-tier and total exposure limits.
type AllocationManager struct {
	config AllocationConfig
}

// NewAllocationManager creates a new AllocationManager with the given config.
func NewAllocationManager(cfg AllocationConfig) *AllocationManager {
	return &AllocationManager{config: cfg}
}

// CheckAllocation checks if an allocation amount is allowed for the given tier.
// Returns true if the amount is within the tier limit.
func (m *AllocationManager) CheckAllocation(tier domain.Tier, amount decimal.Decimal) bool {
	limit := m.getLimitForTier(tier)
	if limit.IsZero() {
		return false // unknown tier -> no allocation allowed
	}
	return amount.LessThanOrEqual(limit)
}

// CheckTotalExposure checks if the total exposure is within allowed limits.
// Returns true if current exposure / budget <= MaxExposure.
func (m *AllocationManager) CheckTotalExposure(current, budget decimal.Decimal) bool {
	if budget.IsZero() {
		return true // no budget -> no exposure check needed
	}
	exposurePct := current.Div(budget)
	return exposurePct.LessThanOrEqual(m.config.MaxExposure)
}

// GetRemainingBudget returns the remaining budget for a tier given current usage.
func (m *AllocationManager) GetRemainingBudget(tier domain.Tier, current decimal.Decimal) decimal.Decimal {
	limit := m.getLimitForTier(tier)
	if limit.IsZero() {
		return decimal.Zero
	}
	remaining := limit.Sub(current)
	if remaining.LessThan(decimal.Zero) {
		return decimal.Zero
	}
	return remaining
}

// getLimitForTier returns the allocation limit for the given tier.
func (m *AllocationManager) getLimitForTier(tier domain.Tier) decimal.Decimal {
	switch tier {
	case domain.TierA:
		return m.config.TierALimit
	case domain.TierB:
		return m.config.TierBLimit
	case domain.TierC:
		return m.config.TierCLimit
	default:
		return decimal.Zero
	}
}