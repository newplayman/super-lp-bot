// Package strategy defines the decision-making interface for pool selection,
// range positioning, and rebalance strategy.
//
// Strategy is a stateless module that consumes bus events from Scanner and
// Audit, and emits position.intent events to the Risk gate. It reads from
// PoolRepo and PositionRepo to make informed decisions.
//
// See spec §3.4 for bus event patterns and §5 for risk gate integration.
package strategy

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// RangeParams defines the tick range for a position.
type RangeParams struct {
	TickLower     int64
	TickUpper     int64
	AmountUSD     domain.Decimal // position size in USD
	Concentrated  bool           // whether to use concentrated liquidity
}

// Intent represents a position opening intention.
type Intent struct {
	PoolID    string
	Chain     domain.ChainID
	Tier      domain.Tier
	Range     RangeParams
	TraceID   string
	Reason    string // human-readable reason for the decision
}

// Strategy is the main interface for position decision-making.
// It consumes pool events and emits position intents.
//
// Implementation should be stateless - all state is read from ports.
type Strategy interface {
	// EvaluatePool assesses whether a pool is a good candidate for positioning.
	// Returns an Intent if the pool passes selection criteria, nil otherwise.
	EvaluatePool(ctx context.Context, pool domain.Pool, score domain.Score) (*Intent, error)

	// EvaluateRebalance checks if an existing position should be rebalanced.
	// Returns a new Intent with adjusted range, nil if no rebalance needed.
	EvaluateRebalance(ctx context.Context, pos domain.Position) (*Intent, error)

	// SelectCandidates returns the top N pools for potential positioning.
	// The selection is based on score, existing positions, and budget constraints.
	SelectCandidates(ctx context.Context, pools []domain.Pool, limit int) ([]domain.Pool, error)
}

// PoolFilter contains criteria for filtering candidate pools.
type PoolFilter struct {
	MinTier      domain.Tier
	MinTVLUSD    domain.Decimal
	MaxPerPoolUSD domain.Decimal
	ExcludeChains []domain.ChainID
}

// DefaultPoolFilter returns the default pool filtering criteria.
func DefaultPoolFilter() PoolFilter {
	return PoolFilter{
		MinTier:        domain.TierC,
		MinTVLUSD:      domain.MustDecimal("10000"), // $10k minimum TVL
		MaxPerPoolUSD:  domain.MustDecimal("50"),    // $50 max per pool in Phase 0
		ExcludeChains:  nil,
	}
}

// RangeCalculator computes optimal tick ranges for positions.
type RangeCalculator interface {
	// CalculateRange computes the tick range for a given pool and tier.
	// Uses the tier's k·σ multiplier for range width.
	CalculateRange(tick int64, volatility float64, tier domain.Tier) RangeParams

	// AdjustRangeForRebalance adjusts an existing range based on current price.
	AdjustRangeForRebalance(currentTick, tickLower, tickUpper int64, breachPct float64) RangeParams
}