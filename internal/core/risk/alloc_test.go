package risk

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

func TestAllocationManager_TierALimit(t *testing.T) {
	manager := NewAllocationManager(DefaultAllocationConfig())

	// Tier A should limit to $1000
	allowed := manager.CheckAllocation(domain.TierA, decimal.NewFromInt(1500))
	require.False(t, allowed, "Tier A allocation of $1500 should be rejected (limit $1000)")

	allowed = manager.CheckAllocation(domain.TierA, decimal.NewFromInt(999))
	require.True(t, allowed, "Tier A allocation of $999 should be allowed")

	allowed = manager.CheckAllocation(domain.TierA, decimal.NewFromInt(1000))
	require.True(t, allowed, "Tier A allocation of exactly $1000 should be allowed")
}

func TestAllocationManager_TierBLimit(t *testing.T) {
	manager := NewAllocationManager(DefaultAllocationConfig())

	// Tier B should limit to $200
	allowed := manager.CheckAllocation(domain.TierB, decimal.NewFromInt(201))
	require.False(t, allowed, "Tier B allocation of $201 should be rejected (limit $200)")

	allowed = manager.CheckAllocation(domain.TierB, decimal.NewFromInt(199))
	require.True(t, allowed, "Tier B allocation of $199 should be allowed")

	allowed = manager.CheckAllocation(domain.TierB, decimal.NewFromInt(200))
	require.True(t, allowed, "Tier B allocation of exactly $200 should be allowed")
}

func TestAllocationManager_TierCLimit(t *testing.T) {
	manager := NewAllocationManager(DefaultAllocationConfig())

	// Tier C should limit to $50
	allowed := manager.CheckAllocation(domain.TierC, decimal.NewFromInt(51))
	require.False(t, allowed, "Tier C allocation of $51 should be rejected (limit $50)")

	allowed = manager.CheckAllocation(domain.TierC, decimal.NewFromInt(49))
	require.True(t, allowed, "Tier C allocation of $49 should be allowed")

	allowed = manager.CheckAllocation(domain.TierC, decimal.NewFromInt(50))
	require.True(t, allowed, "Tier C allocation of exactly $50 should be allowed")
}

func TestAllocationManager_TotalExposureLimit(t *testing.T) {
	manager := NewAllocationManager(DefaultAllocationConfig())

	// Total exposure should not exceed 30%
	budget := decimal.NewFromInt(10000)

	allowed := manager.CheckTotalExposure(decimal.NewFromInt(3500), budget)
	require.False(t, allowed, "35% exposure should be rejected (> 30%)")

	allowed = manager.CheckTotalExposure(decimal.NewFromInt(2500), budget)
	require.True(t, allowed, "25% exposure should be allowed (< 30%)")

	allowed = manager.CheckTotalExposure(decimal.NewFromInt(3000), budget)
	require.True(t, allowed, "Exactly 30% exposure should be allowed")
}

func TestAllocationManager_GetRemainingBudget(t *testing.T) {
	manager := NewAllocationManager(DefaultAllocationConfig())

	// Tier A: $1000 limit, $300 used -> $700 remaining
	remaining := manager.GetRemainingBudget(domain.TierA, decimal.NewFromInt(300))
	require.True(t, remaining.Equal(decimal.NewFromInt(700)), "Tier A remaining budget should be $700")

	// Tier A: $1000 limit, $800 used -> $200 remaining
	remaining = manager.GetRemainingBudget(domain.TierA, decimal.NewFromInt(800))
	require.True(t, remaining.Equal(decimal.NewFromInt(200)), "Tier A remaining budget should be $200")

	// Tier B: $200 limit, $50 used -> $150 remaining
	remaining = manager.GetRemainingBudget(domain.TierB, decimal.NewFromInt(50))
	require.True(t, remaining.Equal(decimal.NewFromInt(150)), "Tier B remaining budget should be $150")

	// Tier C: $50 limit, $20 used -> $30 remaining
	remaining = manager.GetRemainingBudget(domain.TierC, decimal.NewFromInt(20))
	require.True(t, remaining.Equal(decimal.NewFromInt(30)), "Tier C remaining budget should be $30")
}

func TestAllocationManager_UnknownTier(t *testing.T) {
	manager := NewAllocationManager(DefaultAllocationConfig())

	// Unknown tier should default to allowing allocation (conservative)
	// We use an empty tier which is invalid
	unknownTier := domain.Tier("")
	allowed := manager.CheckAllocation(unknownTier, decimal.NewFromInt(100))
	// Unknown tier should return false (no allocation allowed for safety)
	require.False(t, allowed, "Unknown tier should not allow allocation")

	// Remaining budget for unknown tier should be zero
	remaining := manager.GetRemainingBudget(unknownTier, decimal.NewFromInt(0))
	require.True(t, remaining.IsZero(), "Unknown tier remaining budget should be zero")
}

func TestAllocationManager_CustomConfig(t *testing.T) {
	config := AllocationConfig{
		TierALimit:  decimal.NewFromInt(2000),
		TierBLimit:  decimal.NewFromInt(500),
		TierCLimit:  decimal.NewFromInt(100),
		MaxExposure: decimal.NewFromFloat(0.25), // 25%
	}

	manager := NewAllocationManager(config)

	// Custom Tier A limit: $2000
	allowed := manager.CheckAllocation(domain.TierA, decimal.NewFromInt(2000))
	require.True(t, allowed, "Custom Tier A limit $2000 should work")

	allowed = manager.CheckAllocation(domain.TierA, decimal.NewFromInt(2001))
	require.False(t, allowed, "Custom Tier A limit $2001 should be rejected")

	// Custom total exposure: 25%
	budget := decimal.NewFromInt(10000)
	allowed = manager.CheckTotalExposure(decimal.NewFromInt(2500), budget)
	require.True(t, allowed, "Custom 25% exposure should be allowed")

	allowed = manager.CheckTotalExposure(decimal.NewFromInt(2501), budget)
	require.False(t, allowed, "Custom 25.01% exposure should be rejected")
}

func TestDefaultAllocationConfig(t *testing.T) {
	config := DefaultAllocationConfig()

	require.True(t, config.TierALimit.Equal(decimal.NewFromInt(1000)), "Tier A limit should be $1000")
	require.True(t, config.TierBLimit.Equal(decimal.NewFromInt(200)), "Tier B limit should be $200")
	require.True(t, config.TierCLimit.Equal(decimal.NewFromInt(50)), "Tier C limit should be $50")
	require.True(t, config.MaxExposure.Equal(decimal.NewFromFloat(0.30)), "Max exposure should be 30%")
}