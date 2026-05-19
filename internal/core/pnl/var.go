// Package pnl provides profit and loss calculation and risk metrics.
//
// VaR (Value at Risk) calculation uses historical simulation method:
// - Collect historical returns over a lookback period (e.g., 90 days)
// - Sort returns from worst to best
// - VaR at confidence C = percentile at (1-C) from the tail (worst losses)
//
// Thresholds per spec §5.6:
//   - > 8% VaR → Warn (reject new intents)
//   - > 12% VaR → Kill (Watchdog RaiseKill)
package pnl

import (
	"errors"
	"sort"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// VaRConfig configures the VaR calculation parameters.
type VaRConfig struct {
	// ConfidenceLevel is the confidence level for VaR calculation.
	// For example, 0.95 for 95% VaR (5% of returns are worse).
	ConfidenceLevel float64

	// LookbackDays is the number of days to look back for historical returns.
	// For example, 90 days.
	LookbackDays int

	// WarnThreshold is the VaR percentage above which to warn.
	// For example, 0.08 for 8%.
	WarnThreshold decimal.Decimal

	// KillThreshold is the VaR percentage above which to kill.
	// For example, 0.12 for 12%.
	KillThreshold decimal.Decimal
}

// VaRResult contains the result of a VaR calculation.
type VaRResult struct {
	// VaR is the Value at Risk as a decimal fraction.
	// For example, 0.05 means 5% VaR.
	VaR decimal.Decimal

	// Confidence is the confidence level used (e.g., 0.95 for 95%).
	Confidence float64

	// Lookback is the number of days of data used.
	Lookback int

	// UpdatedAt is when this result was calculated.
	UpdatedAt time.Time
}

// ErrEmptyReturns is returned when no returns are provided for VaR calculation.
var ErrEmptyReturns = errors.New("no returns provided")

// CalculateVaR computes portfolio VaR using the historical simulation method.
//
// Historical simulation approach:
//  1. Sort returns from worst (largest loss) to best (largest gain)
//  2. VaR = returns[ceil((1-confidence) * n) - 1]
//  3. VaR is expressed as a positive decimal (e.g., 0.05 = 5% potential loss)
//
// The VaR represents the maximum expected loss over the lookback period
// at the given confidence level. For example, 95% VaR of 0.08 means
// there is a 95% probability that losses will not exceed 8%.
//
// Parameters:
//   - returns: historical portfolio returns as decimal fractions (negative = loss)
//   - config: VaR configuration parameters
//
// Returns VaRResult with the calculated VaR or an error if calculation fails.
func CalculateVaR(returns []decimal.Decimal, config VaRConfig) (VaRResult, error) {
	if len(returns) == 0 {
		return VaRResult{}, ErrEmptyReturns
	}

	// Sort returns from worst (most negative) to best (most positive)
	sorted := make([]decimal.Decimal, len(returns))
	copy(sorted, returns)
	sort.Slice(sorted, func(i, j int) bool {
		return sorted[i].LessThan(sorted[j])
	})

	// Calculate the index for the percentile
	// For 95% confidence, we want the 5th percentile (5% of returns are worse)
	n := len(sorted)
	percentileIndex := (1 - config.ConfidenceLevel) * float64(n)
	index := int(percentileIndex)

	// Handle edge cases for small sample sizes
	if index >= n {
		index = n - 1
	}
	if index < 0 {
		index = 0
	}

	// VaR is the value at the percentile (most negative = worst loss)
	// Since returns are sorted worst to best, we take a negative value (loss)
	// and convert to positive for the VaR (which represents potential loss)
	varValue := sorted[index].Abs()

	return VaRResult{
		VaR:        varValue,
		Confidence: config.ConfidenceLevel,
		Lookback:   config.LookbackDays,
		UpdatedAt:  time.Now(),
	}, nil
}

// GetVaRLevel returns the kill level based on VaR thresholds.
//
// The function evaluates the VaR against configured thresholds:
//   - KillLevelKill: VaR exceeds KillThreshold (> 12%)
//   - KillLevelWarn: VaR exceeds WarnThreshold (> 8%)
//   - KillLevelOK: VaR is within acceptable range
//
// Parameters:
//   - var: the calculated VaR value (as decimal fraction)
//   - config: VaR configuration with threshold values
//
// Returns the appropriate KillLevel based on the VaR thresholds.
func GetVaRLevel(varValue decimal.Decimal, config VaRConfig) ports.KillLevel {
	// Check kill threshold first (more severe)
	if varValue.GreaterThan(config.KillThreshold) {
		return ports.KillLevelKill
	}

	// Check warn threshold
	if varValue.GreaterThan(config.WarnThreshold) {
		return ports.KillLevelWarn
	}

	return ports.KillLevelOK
}

// DefaultVaRConfig returns sensible defaults for VaR calculation.
func DefaultVaRConfig() VaRConfig {
	return VaRConfig{
		ConfidenceLevel: 0.95,
		LookbackDays:    90,
		WarnThreshold:   decimal.NewFromFloat(0.08),  // 8%
		KillThreshold:   decimal.NewFromFloat(0.12),  // 12%
	}
}