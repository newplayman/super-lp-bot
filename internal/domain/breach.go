package domain

import "github.com/shopspring/decimal"

// BreachType represents the type of position breach.
type BreachType string

const (
	BreachTypeRangeBelow BreachType = "range_below"
	BreachTypeRangeAbove BreachType = "range_above"
)

// PositionBreach represents a breach event when position price goes out of range.
type PositionBreach struct {
	PositionID    string
	Type          BreachType
	PriceAtBreach decimal.Decimal
	RangeLower     decimal.Decimal
	RangeUpper     decimal.Decimal
}

// RebalanceReason represents the reason for a rebalance decision.
type RebalanceReason string

const (
	RebalanceReasonRangeBreach    RebalanceReason = "range_breach"
	RebalanceReasonILBreach       RebalanceReason = "il_breach"
	RebalanceReasonVolatilityUp   RebalanceReason = "volatility_up"
	RebalanceReasonManual         RebalanceReason = "manual"
)

// TickRange represents a price tick range.
type TickRange struct {
	TickLower int64
	TickUpper int64
}