package risk

import (
	"context"
	"sync"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// AllocReason represents the reason an allocation was blocked.
type AllocReason string

// Exported AllocReason values for metric labels.
const (
	AllocReasonOK                 AllocReason = "ok"
	AllocReasonOverPoolLimit      AllocReason = "over_pool_limit"
	AllocReasonOverTotalExposure  AllocReason = "over_total_exposure"
	AllocReasonRepoError          AllocReason = "repo_error"
	AllocReasonUnknownTier        AllocReason = "unknown_tier"
	AllocReasonInvalidCandidate   AllocReason = "invalid_candidate"
)

// AllocationCandidate represents a candidate position for allocation.
type AllocationCandidate struct {
	PoolID    string
	Chain     domain.ChainID
	Tier      domain.Tier
	AmountUSD decimal.Decimal
}

// AllocationConfig holds per-tier allocation limits and max exposure.
type AllocationConfig struct {
	TotalCapitalUSD  decimal.Decimal // $1000 (used for exposure calculation)
	TierALimit       decimal.Decimal // max per pool for Tier A (default $1000)
	TierBLimit       decimal.Decimal // max per pool for Tier B (default $200)
	TierCLimit       decimal.Decimal // max per pool for Tier C (default $50)
	MaxExposure      decimal.Decimal // max total exposure as fraction (default 0.30 = 30%)
}

// DefaultAllocationConfig returns sensible defaults per spec §8.5.
func DefaultAllocationConfig() AllocationConfig {
	return AllocationConfig{
		TotalCapitalUSD: decimal.NewFromInt(1000),
		TierALimit:      decimal.NewFromInt(1000),
		TierBLimit:      decimal.NewFromInt(200),
		TierCLimit:      decimal.NewFromInt(50),
		MaxExposure:     decimal.NewFromFloat(0.30), // 30%
	}
}

// AllocationManager enforces per-tier and total exposure limits.
// It uses PositionRepo.Snapshot() to read current positions without caching.
type AllocationManager struct {
	config AllocationConfig
	repo   ports.PositionRepo
	mu     sync.Mutex
}

// NewAllocationManagerWithRepo creates a new AllocationManager with a PositionRepo.
func NewAllocationManagerWithRepo(cfg AllocationConfig, repo ports.PositionRepo) *AllocationManager {
	return &AllocationManager{
		config: cfg,
		repo:   repo,
	}
}

// NewAllocationManager creates a new AllocationManager without a repo (for backwards compatibility).
func NewAllocationManager(cfg AllocationConfig) *AllocationManager {
	return &AllocationManager{
		config: cfg,
		repo:   nil,
	}
}

// CheckAllocationLegacy checks if an allocation amount is allowed for the given tier.
// This is the legacy API for backwards compatibility.
// Returns true if the amount is within the tier limit.
func (m *AllocationManager) CheckAllocationLegacy(tier domain.Tier, amount decimal.Decimal) bool {
	limit := m.getLimitForTier(tier)
	if limit.IsZero() {
		return false // unknown tier -> no allocation allowed
	}
	return amount.LessThanOrEqual(limit)
}

// CheckAllocation checks if an allocation amount is allowed for the given tier.
// Returns true if the amount is within the tier limit.
func (m *AllocationManager) CheckAllocation(tier domain.Tier, amount decimal.Decimal) bool {
	return m.CheckAllocationLegacy(tier, amount)
}

// CheckTotalExposureLegacy checks if the total exposure is within allowed limits.
// This is the legacy API for backwards compatibility.
// Returns true if current exposure / budget <= MaxExposure.
func (m *AllocationManager) CheckTotalExposureLegacy(current, budget decimal.Decimal) bool {
	if budget.IsZero() {
		return true // no budget -> no exposure check needed
	}
	exposurePct := current.Div(budget)
	return exposurePct.LessThanOrEqual(m.config.MaxExposure)
}

// CheckTotalExposure checks if the total exposure is within allowed limits.
// Returns true if current exposure / budget <= MaxExposure.
func (m *AllocationManager) CheckTotalExposure(current, budget decimal.Decimal) bool {
	return m.CheckTotalExposureLegacy(current, budget)
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

// CheckAllocationWithSnapshot checks if adding the candidate would exceed the per-pool limit.
// Uses PositionRepo.Snapshot() for current positions without caching.
// Returns (allowed, reason). Fail-closed: any error returns false.
func (m *AllocationManager) CheckAllocationWithSnapshot(ctx context.Context, c AllocationCandidate) (bool, AllocReason) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Get limit for the candidate's tier
	limit := m.getLimitForTier(c.Tier)
	if limit.IsZero() {
		return false, AllocReasonUnknownTier
	}

	// Get current positions for this pool from repo (no cache)
	var existingTotal decimal.Decimal
	if m.repo != nil {
		positions, err := m.repo.Snapshot(ctx, c.PoolID)
		if err != nil {
			return false, AllocReasonRepoError
		}
		for _, pos := range positions {
			existingTotal = existingTotal.Add(pos.AmountUSD)
		}
	}

	// Check if adding candidate would exceed limit
	newTotal := existingTotal.Add(c.AmountUSD)
	if newTotal.GreaterThan(limit) {
		return false, AllocReasonOverPoolLimit
	}

	return true, AllocReasonOK
}

// CheckTotalExposureWithSnapshot checks if adding the candidate would exceed total exposure limit.
// Uses PositionRepo.Snapshot() for current positions without caching.
// Returns (allowed, reason). Fail-closed: any error returns false.
func (m *AllocationManager) CheckTotalExposureWithSnapshot(ctx context.Context, c AllocationCandidate) (bool, AllocReason) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Calculate current total exposure
	var currentExposure decimal.Decimal
	if m.repo != nil {
		// Get all open positions to calculate total exposure
		positions, err := m.repo.FindByChainAndStatus(ctx, c.Chain, domain.StatusOpen)
		if err != nil {
			return false, AllocReasonRepoError
		}
		for _, pos := range positions {
			currentExposure = currentExposure.Add(pos.AmountUSD)
		}
	}

	// Check if adding candidate would exceed total exposure limit
	newTotal := currentExposure.Add(c.AmountUSD)
	exposurePct := decimal.Zero
	if !m.config.TotalCapitalUSD.IsZero() {
		exposurePct = newTotal.Div(m.config.TotalCapitalUSD)
	}

	if exposurePct.GreaterThan(m.config.MaxExposure) {
		return false, AllocReasonOverTotalExposure
	}

	return true, AllocReasonOK
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