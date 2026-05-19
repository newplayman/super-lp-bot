// Package main provides the lpbot-backtest CLI for Phase 0 validation.
package main

import (
	"fmt"
	"math"

	"github.com/lpbot/lpbot/internal/domain"
)

// ComparisonResult contains the comparison between simulated and actual fees.
type ComparisonResult struct {
	SimulatedFees   domain.Decimal
	GroundTruthFees domain.Decimal
	ErrorPct        float64
	Verdict         string
	ErrorTable      []ErrorRow
}

// ErrorRow represents a single error measurement.
type ErrorRow struct {
	Metric      string
	Simulated   string
	GroundTruth string
	ErrorPct    float64
}

// Compare compares simulated fees with ground truth fees.
// Returns the comparison result with error percentage and verdict.
func Compare(simulatedFees, groundTruthFees domain.Decimal) (*ComparisonResult, error) {
	result := &ComparisonResult{
		SimulatedFees:   simulatedFees,
		GroundTruthFees: groundTruthFees,
	}

	// Calculate error percentage
	// Error% = |simulated - actual| / actual * 100
	if groundTruthFees.IsZero() {
		if simulatedFees.IsZero() {
			result.ErrorPct = 0.0
			result.Verdict = "PASS"
		} else {
			result.ErrorPct = 100.0
			result.Verdict = "FAIL: no ground truth but fees detected"
		}
	} else {
		// Convert to float for comparison using IntPart() + string parsing
		gtFloat := float64(groundTruthFees.IntPart()) / 1e6 // Assuming 6 decimal places
		simFloat := float64(simulatedFees.IntPart()) / 1e6

		if gtFloat == 0 {
			result.ErrorPct = 0.0
		} else {
			result.ErrorPct = math.Abs(simFloat-gtFloat) / math.Abs(gtFloat) * 100
		}

		// Determine verdict based on error threshold
		// Phase 0 threshold: < 5% error is acceptable
		if result.ErrorPct < 5.0 {
			result.Verdict = "PASS"
		} else if result.ErrorPct < 10.0 {
			result.Verdict = "WARN"
		} else {
			result.Verdict = "FAIL"
		}
	}

	// Build error table
	result.ErrorTable = []ErrorRow{
		{
			Metric:      "Total Fees",
			Simulated:   simulatedFees.String(),
			GroundTruth: groundTruthFees.String(),
			ErrorPct:    result.ErrorPct,
		},
	}

	return result, nil
}

// ErrorTable returns the error table as a markdown string.
func (c *ComparisonResult) ErrorTableMarkdown() string {
	s := "| Metric | Simulated | Ground Truth | Error % |\n"
	s += "|---------|-----------|-------------|---------|\n"

	for _, row := range c.ErrorTable {
		s += fmt.Sprintf("| %s | %s | %s | %.2f%% |\n", row.Metric, row.Simulated, row.GroundTruth, row.ErrorPct)
	}

	return s
}