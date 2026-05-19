// Package strategy implements the position decision-making logic.
//
// This is the Phase 0 stub implementation where all methods panic.
// Full implementation arrives in Phase 1 (scanner integration) and Phase 2
// (full decision engine).
//
// See spec §3.4 for data flow and §5 for risk gate integration.
package strategy

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// defaultStrategy is the stub implementation for Phase 0.
type defaultStrategy struct{}

// New creates a new Strategy instance.
// In Phase 0, this returns a stub that panics on all operations.
func New() Strategy {
	return &defaultStrategy{}
}

// EvaluatePool implements Strategy.
// Phase 1 task: T-301
func (s *defaultStrategy) EvaluatePool(ctx context.Context, pool domain.Pool, score domain.Score) (*Intent, error) {
	panic("not implemented: T-301 (Phase 1)")
}

// EvaluateRebalance implements Strategy.
// Phase 2 task: T-401
func (s *defaultStrategy) EvaluateRebalance(ctx context.Context, pos domain.Position) (*Intent, error) {
	panic("not implemented: T-401 (Phase 2)")
}

// SelectCandidates implements Strategy.
// Phase 1 task: T-302
func (s *defaultStrategy) SelectCandidates(ctx context.Context, pools []domain.Pool, limit int) ([]domain.Pool, error) {
	panic("not implemented: T-302 (Phase 1)")
}

// defaultRangeCalculator is the stub implementation for Phase 0.
type defaultRangeCalculator struct{}

// NewRangeCalculator creates a new RangeCalculator.
// In Phase 0, this returns a stub that panics on all operations.
func NewRangeCalculator() RangeCalculator {
	return &defaultRangeCalculator{}
}

// CalculateRange implements RangeCalculator.
// Phase 1 task: T-303
func (c *defaultRangeCalculator) CalculateRange(tick int64, volatility float64, tier domain.Tier) RangeParams {
	panic("not implemented: T-303 (Phase 1)")
}

// AdjustRangeForRebalance implements RangeCalculator.
// Phase 2 task: T-402
func (c *defaultRangeCalculator) AdjustRangeForRebalance(currentTick, tickLower, tickUpper int64, breachPct float64) RangeParams {
	panic("not implemented: T-402 (Phase 2)")
}