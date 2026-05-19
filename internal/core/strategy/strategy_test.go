package strategy_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/core/strategy"
)

// TestStrategyNotImplemented - Phase 0 scaffold test
// Invariants (spec §9.2): #1 (total nominal exposure ≤ cap), #2 (no duplicate active position per pool)
func TestStrategyNotImplemented(t *testing.T) {
	// Phase 0: Strategy stub should exist but panic on operations
	s := strategy.New()
	if s == nil {
		t.Fatal("strategy.New() returned nil")
	}
	// Skip actual operation tests - they will panic as expected
	t.Skip("Phase 1 task T-313: implement EvaluatePool")
}

func TestRangeCalculatorNotImplemented(t *testing.T) {
	// Phase 0: RangeCalculator stub should exist but panic on operations
	c := strategy.NewRangeCalculator()
	if c == nil {
		t.Fatal("strategy.NewRangeCalculator() returned nil")
	}
	// Skip actual operation tests - they will panic as expected
	t.Skip("Phase 1 task T-303: implement CalculateRange")
}

func TestDefaultPoolFilter(t *testing.T) {
	// DefaultPoolFilter should return valid defaults even in Phase 0
	f := strategy.DefaultPoolFilter()
	if f.MinTier == "" {
		t.Error("DefaultPoolFilter() returned empty MinTier")
	}
}
