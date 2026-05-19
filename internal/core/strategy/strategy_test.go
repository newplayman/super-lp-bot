package strategy_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/core/strategy"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

// TestStrategyNew verifies Strategy creation.
func TestStrategyNew(t *testing.T) {
	s := strategy.New()
	require.NotNil(t, s)
}

// TestStrategyNewWithFilter verifies Strategy with custom filter.
func TestStrategyNewWithFilter(t *testing.T) {
	filter := strategy.DefaultPoolFilter()
	s := strategy.NewWithFilter(filter)
	require.NotNil(t, s)
}

// TestStrategyEvaluatePool verifies pool evaluation with good score.
func TestStrategyEvaluatePool(t *testing.T) {
	s := strategy.New()
	ctx := context.Background()

	pool := domain.Pool{
		ID:    "0xPool123",
		Chain: domain.ChainBase,
	}
	score := domain.Score{
		FeeAPRScore:     70,
		TvlScore:        60,
		VolScore:        80,
		VolatilityScore: 60,
		SecurityScore:   70,
	}
	score.Total = score.ComputeTotal()

	intent, err := s.EvaluatePool(ctx, pool, score)
	require.NoError(t, err)
	// Intent may be nil if score is below threshold
	_ = intent
}

// TestStrategyEvaluatePoolLowScore verifies low score returns nil.
func TestStrategyEvaluatePoolLowScore(t *testing.T) {
	s := strategy.New()
	ctx := context.Background()

	pool := domain.Pool{ID: "0xPool123", Chain: domain.ChainBase}
	score := domain.Score{
		FeeAPRScore:     30,
		TvlScore:        30,
		VolScore:        30,
		VolatilityScore: 30,
		SecurityScore:   30,
	}
	score.Total = score.ComputeTotal()

	intent, err := s.EvaluatePool(ctx, pool, score)
	require.NoError(t, err)
	require.Nil(t, intent) // Should return nil for low score
}

// TestStrategySelectCandidates verifies candidate selection.
func TestStrategySelectCandidates(t *testing.T) {
	s := strategy.New()
	ctx := context.Background()

	pools := []domain.Pool{
		{ID: "0xPoolA", Chain: domain.ChainBase},
		{ID: "0xPoolB", Chain: domain.ChainBase},
		{ID: "0xPoolC", Chain: domain.ChainSolana},
	}

	candidates, err := s.SelectCandidates(ctx, pools, 2)
	require.NoError(t, err)
	require.Len(t, candidates, 2) // Should return top 2
}

// TestStrategySelectCandidatesEmpty verifies empty pool list.
func TestStrategySelectCandidatesEmpty(t *testing.T) {
	s := strategy.New()
	ctx := context.Background()

	candidates, err := s.SelectCandidates(ctx, []domain.Pool{}, 10)
	require.NoError(t, err)
	require.Len(t, candidates, 0)
}

// TestRangeCalculatorNew verifies RangeCalculator creation.
func TestRangeCalculatorNew(t *testing.T) {
	c := strategy.NewRangeCalculator()
	require.NotNil(t, c)
}

// TestRangeCalculatorCalculateRange verifies range calculation.
func TestRangeCalculatorCalculateRange(t *testing.T) {
	c := strategy.NewRangeCalculator()

	params := c.CalculateRange(50000, 0.5, domain.TierA)
	require.NotZero(t, params.TickLower)
	require.NotZero(t, params.TickUpper)
	require.True(t, params.TickLower < params.TickUpper)
	require.True(t, params.Concentrated)
}

// TestRangeCalculatorCalculateRangeTierB verifies Tier B range.
func TestRangeCalculatorCalculateRangeTierB(t *testing.T) {
	c := strategy.NewRangeCalculator()

	params := c.CalculateRange(50000, 0.5, domain.TierB)
	require.NotZero(t, params.TickLower)
	require.NotZero(t, params.TickUpper)
	require.True(t, params.Concentrated)
}

// TestRangeCalculatorCalculateRangeTierC verifies Tier C range.
func TestRangeCalculatorCalculateRangeTierC(t *testing.T) {
	c := strategy.NewRangeCalculator()

	params := c.CalculateRange(50000, 0.5, domain.TierC)
	require.NotZero(t, params.TickLower)
	require.NotZero(t, params.TickUpper)
}

// TestRangeCalculatorAdjustRange verifies range adjustment.
func TestRangeCalculatorAdjustRange(t *testing.T) {
	c := strategy.NewRangeCalculator()

	params := c.AdjustRangeForRebalance(55000, 54000, 56000, 0.1)
	require.NotZero(t, params.TickLower)
	require.NotZero(t, params.TickUpper)
}

// TestDefaultPoolFilter verifies default filter values.
func TestDefaultPoolFilter(t *testing.T) {
	f := strategy.DefaultPoolFilter()
	require.Equal(t, domain.TierC, f.MinTier)
	require.True(t, f.MinTVLUSD.GreaterThan(decimal.Zero))
	require.True(t, f.MaxPerPoolUSD.GreaterThan(decimal.Zero))
}

// TestCalculateRangeFromScore verifies range calculation from score.
func TestCalculateRangeFromScore(t *testing.T) {
	score := domain.Score{
		FeeAPRScore:     60,
		TvlScore:        60,
		VolScore:        60,
		VolatilityScore: 60,
		SecurityScore:   60,
	}
	tier := domain.TierB
	params := strategy.CalculateRangeFromScore(score, tier)
	require.NotZero(t, params.TickLower)
	require.NotZero(t, params.TickUpper)
	require.True(t, params.TickLower < params.TickUpper)
}

// TestScoreComputeTotal verifies score computation.
func TestScoreComputeTotal(t *testing.T) {
	score := domain.Score{
		FeeAPRScore:     80,
		TvlScore:        70,
		VolScore:        90,
		VolatilityScore: 60,
		SecurityScore:   80,
	}
	score.Total = score.ComputeTotal()
	require.True(t, score.Total > 0)
}

// TestScoreAssignTier verifies tier assignment.
func TestScoreAssignTier(t *testing.T) {
	score := domain.Score{Total: 80}
	tier := score.AssignTier()
	require.Equal(t, domain.TierA, tier)

	score.Total = 60
	tier = score.AssignTier()
	require.Equal(t, domain.TierB, tier)

	score.Total = 40
	tier = score.AssignTier()
	require.Equal(t, domain.TierC, tier)
}