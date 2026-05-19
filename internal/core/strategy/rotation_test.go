package strategy

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestRotationCandidateScorer_FeeDecay(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	// New pool with high fees = high score
	candidate := PoolWithScore{
		Pool: domain.Pool{
			ID:    "pool-new",
			Chain: domain.ChainBase,
		},
		Score: domain.Score{
			FeeAPRScore: 80,
			VolScore:    70,
			Total:       75,
		},
	}

	score := scorer.ScoreCandidate(candidate, time.Now())
	require.True(t, score > 70, "New pool should have high score, got: %v", score)
}

func TestRotationCandidateScorer_AgedPool(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	// Old pool with same metrics = lower score due to fee decay
	candidate := PoolWithScore{
		Pool: domain.Pool{
			ID:    "pool-old",
			Chain: domain.ChainBase,
		},
		Score: domain.Score{
			FeeAPRScore: 80,
			VolScore:    70,
			Total:       75,
		},
	}

	oldScore := scorer.ScoreCandidate(candidate, time.Now().Add(-30*24*time.Hour)) // 30 days old
	newScore := scorer.ScoreCandidate(candidate, time.Now())

	require.True(t, oldScore < newScore, "Aged pool should score lower due to fee decay: old=%v, new=%v", oldScore, newScore)
}

func TestRotationScorer_ShouldRotate(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(), // 30 days old, beyond min hold
		},
		Score: domain.Score{
			FeeAPRScore: 40, // Low performing
			VolScore:    30,
			Total:       35,
		},
	}

	candidates := []PoolWithScore{
		{
			Pool: domain.Pool{ID: "pool-new", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 80, VolScore: 70, Total: 75},
		},
	}

	should, target := scorer.ShouldRotate(context.Background(), current, candidates)
	require.True(t, should, "Should rotate when better candidate exists")
	require.NotNil(t, target)
	require.Equal(t, "pool-new", target.Pool.ID)
}

func TestRotationScorer_ShouldNotRotate_SameScore(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(),
		},
		Score: domain.Score{
			FeeAPRScore: 80,
			VolScore:    70,
			Total:       75,
		},
	}

	// Same score candidates
	candidates := []PoolWithScore{
		{
			Pool: domain.Pool{ID: "pool-new", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 80, VolScore: 70, Total: 75},
		},
	}

	should, _ := scorer.ShouldRotate(context.Background(), current, candidates)
	require.False(t, should, "Should not rotate when score is same")
}

func TestRotationScorer_MinHoldPeriod(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	// Recently opened position (below min hold period)
	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-1*24*time.Hour).Unix(), // 1 day ago
		},
		Score: domain.Score{
			FeeAPRScore: 20, // Low performing
			VolScore:    10,
			Total:       15,
		},
	}

	candidates := []PoolWithScore{
		{
			Pool: domain.Pool{ID: "pool-new", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 80, VolScore: 70, Total: 75},
		},
	}

	should, _ := scorer.ShouldRotate(context.Background(), current, candidates)
	require.False(t, should, "Should not rotate if min hold period not met")
}

func TestRotationScorer_MinScoreDelta(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(), // 30 days old, beyond min hold
		},
		Score: domain.Score{
			FeeAPRScore: 65, // Marginally lower than candidate
			VolScore:    60,
			Total:       62,
		},
	}

	// Only slightly better candidate
	candidates := []PoolWithScore{
		{
			Pool: domain.Pool{ID: "pool-new", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 68, VolScore: 65, Total: 67},
		},
	}

	should, _ := scorer.ShouldRotate(context.Background(), current, candidates)
	require.False(t, should, "Should not rotate if improvement is below MinScoreDelta")
}

func TestRotationScorer_NoCandidates(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(),
		},
		Score: domain.Score{
			FeeAPRScore: 40,
			VolScore:    30,
			Total:       35,
		},
	}

	should, _ := scorer.ShouldRotate(context.Background(), current, nil)
	require.False(t, should, "Should not rotate with no candidates")
}

func TestDefaultRotationConfig(t *testing.T) {
	cfg := DefaultRotationConfig()
	require.Equal(t, 0.5, cfg.FeeDecayRate)
	require.Equal(t, 10.0, cfg.MinScoreDelta)
	require.Equal(t, 7, cfg.MinHoldDays)
}

func TestRotationScorer_EmptyCandidateList(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(),
		},
		Score: domain.Score{
			FeeAPRScore: 40,
			VolScore:    30,
			Total:       35,
		},
	}

	should, _ := scorer.ShouldRotate(context.Background(), current, []PoolWithScore{})
	require.False(t, should, "Should not rotate with empty candidates")
}

func TestRotationScorer_SelectBestCandidate(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(),
		},
		Score: domain.Score{
			FeeAPRScore: 40,
			VolScore:    30,
			Total:       35,
		},
	}

	// Multiple candidates - should select the best one
	candidates := []PoolWithScore{
		{
			Pool: domain.Pool{ID: "pool-low", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 50, VolScore: 50, Total: 50},
		},
		{
			Pool: domain.Pool{ID: "pool-high", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 90, VolScore: 85, Total: 88},
		},
		{
			Pool: domain.Pool{ID: "pool-mid", Chain: domain.ChainBase},
			Score: domain.Score{FeeAPRScore: 70, VolScore: 65, Total: 68},
		},
	}

	should, target := scorer.ShouldRotate(context.Background(), current, candidates)
	require.True(t, should, "Should rotate to best candidate")
	require.NotNil(t, target)
	require.Equal(t, "pool-high", target.Pool.ID)
}

func TestRotationScorer_ScoreComponents(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	// Test scoring with different score totals
	candidate := PoolWithScore{
		Pool: domain.Pool{
			ID:    "pool-test",
			Chain: domain.ChainBase,
		},
		Score: domain.Score{
			FeeAPRScore: 50,
			VolScore:    50,
			Total:       50,
		},
	}

	score := scorer.ScoreCandidate(candidate, time.Now())
	require.InDelta(t, 50.0, score, 0.01, "Score should match total score for new pool")
}

func TestRotationScorer_CurrentScore(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	// Test that current position score is used correctly
	current := PositionWithScore{
		Position: domain.Position{
			PoolID:   "pool-1",
			Chain:    domain.ChainBase,
			OpenedAt: time.Now().Add(-30*24*time.Hour).Unix(),
		},
		Score: domain.Score{
			FeeAPRScore: 60,
			VolScore:    60,
			Total:       60,
		},
	}

	// Current score should be 60
	score := scorer.CurrentScore(current)
	require.Equal(t, 60.0, score, "Current score should match position score total")
}

func TestRotationScorer_CandidateScore(t *testing.T) {
	scorer := NewRotationScorer(DefaultRotationConfig())

	// Test candidate scoring
	candidate := PoolWithScore{
		Pool: domain.Pool{
			ID:    "pool-test",
			Chain: domain.ChainBase,
			UpdatedAt: time.Now().Unix(),
		},
		Score: domain.Score{
			FeeAPRScore: 70,
			VolScore:    70,
			Total:       70,
		},
	}

	score := scorer.CandidateScore(candidate)
	require.Equal(t, 70.0, score, "Candidate score should match total score")
}