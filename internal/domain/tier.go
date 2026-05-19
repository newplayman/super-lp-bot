package domain

import (
	"fmt"

	"github.com/shopspring/decimal"
)

// Tier classification for pools (spec §3.1)
type Tier string

const (
	TierA Tier = "A"
	TierB Tier = "B"
	TierC Tier = "C"
)

func (t Tier) String() string { return string(t) }

func ParseTier(s string) (Tier, error) {
	switch s {
	case "A", "a":
		return TierA, nil
	case "B", "b":
		return TierB, nil
	case "C", "c":
		return TierC, nil
	default:
		return "", fmt.Errorf("unknown tier: %q", s)
	}
}

// TierThresholds holds risk thresholds per tier.
type TierThresholds struct {
	ILStopPct        Decimal  // IL stop percentage
	RangeKSigma      Decimal  // range k·σ multiplier
	MinHoldHours     Decimal  // minimum hold time in hours
	MaxPerPoolUSD    Decimal  // max exposure per pool in USD
}

func TierThresholdsFor(t Tier) TierThresholds {
	switch t {
	case TierA:
		return TierThresholds{
			ILStopPct:     MustDecimal("0.03"),  // 3%
			RangeKSigma:   MustDecimal("1.75"),
			MinHoldHours:  MustDecimal("6"),
			MaxPerPoolUSD: MustDecimal("1000"),
		}
	case TierB:
		return TierThresholds{
			ILStopPct:     MustDecimal("0.05"),  // 5%
			RangeKSigma:   MustDecimal("1.25"),
			MinHoldHours:  MustDecimal("2"),
			MaxPerPoolUSD: MustDecimal("200"),
		}
	case TierC:
		return TierThresholds{
			ILStopPct:     MustDecimal("0.08"),  // 8%
			RangeKSigma:   MustDecimal("0.75"),
			MinHoldHours:  MustDecimal("0.5"),
			MaxPerPoolUSD: MustDecimal("50"),
		}
	}
	return TierThresholds{}
}

// Decimal is an alias to shopspring/decimal for domain-specific decimal types.
type Decimal = decimal.Decimal

// MustDecimal parses a decimal string or panics.
func MustDecimal(s string) Decimal {
	d, err := decimal.NewFromString(s)
	if err != nil {
		panic("invalid decimal: " + s)
	}
	return d
}
