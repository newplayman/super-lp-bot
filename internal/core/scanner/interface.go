// Package scanner provides the Scanner interface for pool discovery and scoring.
package scanner

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// Scanner scans candidate pools and publishes scored events (spec §3.1).
type Scanner interface {
	// Run starts the scanner loop. It blocks until ctx is cancelled.
	Run(ctx context.Context) error

	// Score evaluates a pool and returns its score (spec §3.1).
	Score(ctx context.Context, p domain.Pool) (domain.Score, error)

	// AssignTier derives a Tier from a score.
	AssignTier(s domain.Score) domain.Tier
}