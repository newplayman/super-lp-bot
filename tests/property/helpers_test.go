// Package property provides property-based tests for domain logic.
package property

import (
	"testing"

	"github.com/shopspring/decimal"
	"pgregory.net/rapid"

	"github.com/lpbot/lpbot/internal/domain"
)

// TestChainIDGenerators verifies ChainID generators produce valid values.
func TestChainIDGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		chainID := GenChainID().Draw(t, "ChainID")
		if chainID != domain.ChainBase && chainID != domain.ChainSolana {
			t.Errorf("invalid ChainID: %v", chainID)
		}
	})
}

// TestTierGenerators verifies Tier generators produce valid values.
func TestTierGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		tier := GenTier().Draw(t, "Tier")
		if tier != domain.TierA && tier != domain.TierB && tier != domain.TierC {
			t.Errorf("invalid Tier: %v", tier)
		}
	})
}

// TestPositionGenerators verifies Position generators produce valid positions.
func TestPositionGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		pos := GenPosition().Draw(t, "Position")

		// Verify tick range is valid (lower < upper)
		if pos.TickLower >= pos.TickUpper {
			t.Errorf("invalid tick range: lower=%d upper=%d", pos.TickLower, pos.TickUpper)
		}

		// Verify tick bounds
		if pos.TickLower < -887272 || pos.TickLower > 887272 {
			t.Errorf("TickLower out of bounds: %d", pos.TickLower)
		}
		if pos.TickUpper < -887272 || pos.TickUpper > 887272 {
			t.Errorf("TickUpper out of bounds: %d", pos.TickUpper)
		}

		// Verify status is valid
		validStatuses := map[domain.PositionStatus]bool{
			domain.StatusIntended:   true,
			domain.StatusApproved:   true,
			domain.StatusRejected:   true,
			domain.StatusOpening:    true,
			domain.StatusOpen:       true,
			domain.StatusExiting:    true,
			domain.StatusClosed:     true,
			domain.StatusExitFailed: true,
			domain.StatusManual:     true,
		}
		if !validStatuses[pos.Status] {
			t.Errorf("invalid PositionStatus: %v", pos.Status)
		}

		// Verify AmountUSD is positive
		if !pos.AmountUSD.IsPositive() {
			t.Errorf("AmountUSD should be positive: %v", pos.AmountUSD)
		}
	})
}

// TestPoolGenerators verifies Pool generators produce valid pools.
func TestPoolGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		pool := GenPool().Draw(t, "Pool")

		// Verify FeeBPS is in valid range
		if pool.FeeBPS < 1 || pool.FeeBPS > 10000 {
			t.Errorf("FeeBPS out of bounds: %d", pool.FeeBPS)
		}

		// Verify Tier is valid
		if pool.Tier_ != domain.TierA && pool.Tier_ != domain.TierB && pool.Tier_ != domain.TierC {
			t.Errorf("invalid Tier: %v", pool.Tier_)
		}

		// Verify addresses are not zero
		if pool.Token0.IsZero() {
			t.Error("Token0 should not be zero")
		}
		if pool.Token1.IsZero() {
			t.Error("Token1 should not be zero")
		}
	})
}

// TestDecimalGenerators verifies decimal generators produce valid values.
func TestDecimalGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		val := GenDecimal(5).Draw(t, "Decimal")
		// Should be in range -10^5 to 10^5
		if val.GreaterThan(domain.Decimal(decimal.NewFromInt(100000))) || val.LessThan(domain.Decimal(decimal.NewFromInt(-100000))) {
			t.Errorf("Decimal out of expected range: %v", val)
		}
	})
}

// TestPositiveDecimalGenerators verifies positive decimal generators produce valid values.
func TestPositiveDecimalGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		val := GenPositiveDecimal(8).Draw(t, "PositiveDecimal")
		if !val.IsPositive() {
			t.Errorf("should be positive: %v", val)
		}
		// Should be in range 1 to 10^8
		if val.LessThan(domain.Decimal(decimal.NewFromInt(1))) {
			t.Errorf("should be >= 1: %v", val)
		}
	})
}

// TestTickGenerators verifies tick generators produce valid ticks.
func TestTickGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		tick := GenTick().Draw(t, "Tick")
		if tick < -887272 || tick > 887272 {
			t.Errorf("Tick out of bounds: %d", tick)
		}
	})
}

// TestTickRangeGenerators verifies tick range generators produce valid ranges.
func TestTickRangeGenerators(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		tr := GenTickRange().Draw(t, "TickRange")
		if tr.Lower >= tr.Upper {
			t.Errorf("invalid tick range: lower=%d upper=%d", tr.Lower, tr.Upper)
		}
	})
}