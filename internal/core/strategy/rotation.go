package strategy

import (
	"context"
	"math"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
)

// PoolWithScore combines pool information with its score.
type PoolWithScore struct {
	Pool  domain.Pool
	Score domain.Score
}

// PositionWithScore combines position information with its score.
type PositionWithScore struct {
	domain.Position
	Score domain.Score
}

// RotationDecision represents the outcome of a rotation evaluation.
type RotationDecision struct {
	ShouldRotate bool
	TargetPool   string
	Reason       string
	CurrentScore float64
	TargetScore  float64
}

// RotationConfig contains configuration for the rotation strategy.
type RotationConfig struct {
	// FeeDecayRate is the daily decay rate applied to pool scores (0-1).
	// Higher values mean faster score decay for aged pools.
	FeeDecayRate float64

	// MinScoreDelta is the minimum score improvement required to rotate.
	MinScoreDelta float64

	// MinHoldDays is the minimum number of days a position must be held
	// before it can be rotated out.
	MinHoldDays int
}

// DefaultRotationConfig returns the default rotation configuration.
func DefaultRotationConfig() RotationConfig {
	return RotationConfig{
		FeeDecayRate:  0.5,  // 50% decay per day (aggressive for testing)
		MinScoreDelta: 10.0, // Require at least 10 point improvement
		MinHoldDays:   7,    // Hold for at least 7 days
	}
}

// RotationScorer evaluates candidate pools for rotation and determines
// whether an existing position should be rotated out.
type RotationScorer struct {
	config RotationConfig
}

// NewRotationScorer creates a new RotationScorer with the given configuration.
func NewRotationScorer(cfg RotationConfig) *RotationScorer {
	return &RotationScorer{config: cfg}
}

// ScoreCandidate calculates the adjusted score for a candidate pool.
// It applies fee decay based on the pool's age - newer pools score higher.
func (s *RotationScorer) ScoreCandidate(candidate PoolWithScore, age time.Time) float64 {
	// Use the total score from the Score struct
	baseScore := candidate.Score.Total

	// Calculate age in days
	ageDays := time.Since(age).Hours() / 24

	// Apply exponential decay based on age
	decayFactor := math.Pow(1-s.config.FeeDecayRate/10, ageDays) // Scaled decay
	if decayFactor < 0.1 {
		decayFactor = 0.1 // Minimum 10% of original score
	}

	adjustedScore := baseScore * decayFactor
	return adjustedScore
}

// ShouldRotate determines whether the current position should be rotated
// to one of the candidate pools.
func (s *RotationScorer) ShouldRotate(ctx context.Context, current PositionWithScore, candidates []PoolWithScore) (bool, *PoolWithScore) {
	// No candidates means no rotation
	if len(candidates) == 0 {
		return false, nil
	}

	// Check if position has been held long enough
	if !s.canRotate(current.Position) {
		return false, nil
	}

	// Get current position's score
	currentScore := s.CurrentScore(current)

	// Find the best candidate
	var bestCandidate *PoolWithScore
	bestScore := currentScore

	for i := range candidates {
		candidateScore := s.CandidateScore(candidates[i])
		if candidateScore > bestScore {
			bestScore = candidateScore
			bestCandidate = &candidates[i]
		}
	}

	// If no candidate beats current score by enough margin, don't rotate
	if bestCandidate == nil {
		return false, nil
	}

	// Check if the improvement meets the minimum threshold
	improvement := bestScore - currentScore
	if improvement < s.config.MinScoreDelta {
		return false, nil
	}

	return true, bestCandidate
}

// canRotate checks if a position can be rotated based on the minimum hold period.
func (s *RotationScorer) canRotate(pos domain.Position) bool {
	if pos.OpenedAt == 0 {
		return true // No timestamp means it can be rotated
	}

	openedTime := time.Unix(pos.OpenedAt, 0)
	daysSinceOpen := time.Since(openedTime).Hours() / 24

	return daysSinceOpen >= float64(s.config.MinHoldDays)
}

// CurrentScore returns the current score for a position (used in ShouldRotate).
func (s *RotationScorer) CurrentScore(pos PositionWithScore) float64 {
	return pos.Score.Total
}

// CandidateScore returns the raw score for a candidate pool.
func (s *RotationScorer) CandidateScore(candidate PoolWithScore) float64 {
	return candidate.Score.Total
}