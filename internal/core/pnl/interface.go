// Package pnl provides profit and loss calculation services for LP positions.
// It handles real-time mark-to-market valuation, realized PnL, and impermanent loss (IL).
//
// Core interfaces defined here:
//   - PnLTracker: main interface for position PnL tracking
//   - PriceSource: price feed abstraction for valuations
//
// See spec §5.5 and M13 in PRD.
package pnl

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/pkg/decimal"
)

// PriceSource provides current prices for token pairs.
// Used for mark-to-market calculations.
type PriceSource interface {
	// GetPrice returns the current price for a token pair in USD.
	// Returns decimal.Zero if price unavailable.
	GetPrice(ctx context.Context, token0, token1 string) (price0USD, price1USD decimal.Decimal, err error)
}

// PnLResult contains the breakdown of a position's PnL.
type PnLResult struct {
	// FeeUSD is the realized fee income (non-negative).
	FeeUSD decimal.Decimal
	// ILUSD is the impermanent loss (non-positive).
	ILUSD decimal.Decimal
	// NetPnLUSD is fee + IL (can be positive or negative).
	NetPnLUSD decimal.Decimal
}

// PositionSnapshot represents a point-in-time valuation of a position.
type PositionSnapshot struct {
	PositionID   string
	ValuationUSD decimal.Decimal
	FeeUSD       decimal.Decimal
	ILUSD        decimal.Decimal
	NetPnLUSD    decimal.Decimal
	BlockRef     domain.BlockRef
}

// PnLTracker is the main interface for tracking position profit and loss.
// It subscribes to position events and maintains real-time valuations.
//
// Implementation note: PnLTracker methods are safe for concurrent use.
type PnLTracker interface {
	// MarkPrice updates the mark-to-market valuation for all tracked positions.
	// Called periodically (e.g., every block or N seconds).
	// Returns the number of positions updated.
	MarkPrice(ctx context.Context) (int, error)

	// GetPositionPnL returns the current PnL breakdown for a position.
	// Returns nil if position is not tracked.
	GetPositionPnL(ctx context.Context, positionID string) (*PnLResult, error)

	// GetPositionSnapshot returns a point-in-time snapshot for a position.
	GetPositionSnapshot(ctx context.Context, positionID string) (*PositionSnapshot, error)

	// RecordRealizedPnL records the realized PnL when a position closes.
	// This writes ledger entries for fee, IL, and other components.
	RecordRealizedPnL(ctx context.Context, positionID string, txHash string) (*PnLResult, error)

	// TrackPosition starts tracking a new position for PnL calculations.
	// Called when position.opened event is received.
	TrackPosition(ctx context.Context, pos *domain.Position) error

	// UntrackPosition stops tracking a position (e.g., after close).
	UntrackPosition(ctx context.Context, positionID string) error
}

// defaultPnL implements PnLTracker with panic stubs for Phase 0.
// Full implementation comes in Phase 1.
type defaultPnL struct {
	priceSource PriceSource
}

// NewDefaultPnL creates a new default PnL implementation.
func NewDefaultPnL(priceSource PriceSource) PnLTracker {
	return &defaultPnL{priceSource: priceSource}
}

// MarkPrice implements PnLTracker.
func (p *defaultPnL) MarkPrice(ctx context.Context) (int, error) {
	panic("not implemented")
}

// GetPositionPnL implements PnLTracker.
func (p *defaultPnL) GetPositionPnL(ctx context.Context, positionID string) (*PnLResult, error) {
	panic("not implemented")
}

// GetPositionSnapshot implements PnLTracker.
func (p *defaultPnL) GetPositionSnapshot(ctx context.Context, positionID string) (*PositionSnapshot, error) {
	panic("not implemented")
}

// RecordRealizedPnL implements PnLTracker.
func (p *defaultPnL) RecordRealizedPnL(ctx context.Context, positionID string, txHash string) (*PnLResult, error) {
	panic("not implemented")
}

// TrackPosition implements PnLTracker.
func (p *defaultPnL) TrackPosition(ctx context.Context, pos *domain.Position) error {
	panic("not implemented")
}

// UntrackPosition implements PnLTracker.
func (p *defaultPnL) UntrackPosition(ctx context.Context, positionID string) error {
	panic("not implemented")
}