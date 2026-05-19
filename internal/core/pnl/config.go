package pnl

import (
	"time"

	"github.com/lpbot/lpbot/internal/domain"
)

// PnLConfig configures PnL tracker behavior.
type PnLConfig struct {
	// MarkInterval is the interval between mark-to-market updates.
	// Used for scheduling periodic mark updates.
	MarkInterval time.Duration

	// ILEnabled enables impermanent loss calculation.
	// Can be disabled for simplified tracking.
	ILEnabled bool
}

// DefaultPnLConfig returns a sensible default configuration.
func DefaultPnLConfig() PnLConfig {
	return PnLConfig{
		MarkInterval: 15 * time.Second,
		ILEnabled:   true,
	}
}

// trackedPosition holds state for a position being tracked.
type trackedPosition struct {
	position  *domain.Position
	lastMark  *PositionSnapshot
	feeAccrued domain.Decimal
	peakValue domain.Decimal
}

// newTrackedPosition creates a new tracked position.
func newTrackedPosition(pos *domain.Position) *trackedPosition {
	return &trackedPosition{
		position:   pos,
		lastMark:   nil,
		feeAccrued: domain.MustDecimal("0"),
		peakValue:  domain.MustDecimal("0"),
	}
}