// Package main provides the lpbot-backtest CLI for Phase 0 validation.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
)

// OutputDir is the directory for output files.
const OutputDir = "./backtest_output"

// GenerateOutputs generates the output files for the backtest.
func GenerateOutputs(outputDir string, result *SimulationResult, comparison *ComparisonResult, pool domain.Pool) error {
	// Create output directory
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return fmt.Errorf("create output dir: %w", err)
	}

	// Generate verdict.md
	if err := generateVerdict(outputDir, comparison, result, pool); err != nil {
		return fmt.Errorf("generate verdict.md: %w", err)
	}

	// Generate pnl_series.csv
	if err := generatePnLSeries(outputDir, result); err != nil {
		return fmt.Errorf("generate pnl_series.csv: %w", err)
	}

	// Generate summary.json
	if err := generateSummary(outputDir, result, comparison, pool); err != nil {
		return fmt.Errorf("generate summary.json: %w", err)
	}

	return nil
}

// generateVerdict creates the verdict.md file with error table.
func generateVerdict(dir string, comparison *ComparisonResult, result *SimulationResult, pool domain.Pool) error {
	var sb strings.Builder

	sb.WriteString("# Backtest Verdict\n\n")
	sb.WriteString(fmt.Sprintf("**Pool:** %s\n\n", pool.ID))
	sb.WriteString(fmt.Sprintf("**Chain:** %s\n\n", pool.Chain))
	sb.WriteString(fmt.Sprintf("**Period:** %s - %s\n\n",
		time.Unix(result.EntryBlockRef.TimeUnix, 0).Format(time.RFC3339),
		time.Unix(result.ExitBlockRef.TimeUnix, 0).Format(time.RFC3339)))
	sb.WriteString(fmt.Sprintf("**Range Mode:** %s\n\n", "symmetric"))
	sb.WriteString("---\n\n")
	sb.WriteString("## Error Table\n\n")

	sb.WriteString("| Metric | Simulated | Ground Truth | Error % |\n")
	sb.WriteString("|---------|-----------|-------------|---------|\n")
	sb.WriteString(fmt.Sprintf("| Total Fees | %s | %s | %.2f%% |\n",
		comparison.SimulatedFees.String(),
		comparison.GroundTruthFees.String(),
		comparison.ErrorPct))
	sb.WriteString(fmt.Sprintf("| Impermanent Loss | %s | - | - |\n",
		result.TotalIL.String()))
	sb.WriteString(fmt.Sprintf("| Net PnL | %s | - | - |\n",
		result.NetPnL.String()))

	sb.WriteString("\n## Verdict\n\n")
	sb.WriteString(fmt.Sprintf("**Status:** %s\n\n", comparison.Verdict))
	sb.WriteString("---\n\n")
	sb.WriteString("## Position Details\n\n")
	sb.WriteString(fmt.Sprintf("- Position ID: %s\n", result.Position.ID))
	sb.WriteString(fmt.Sprintf("- Tick Lower: %d\n", result.Position.TickLower))
	sb.WriteString(fmt.Sprintf("- Tick Upper: %d\n", result.Position.TickUpper))
	sb.WriteString(fmt.Sprintf("- Entry Block: %d\n", result.EntryBlockRef.Number))
	sb.WriteString(fmt.Sprintf("- Exit Block: %d\n", result.ExitBlockRef.Number))

	sb.WriteString("\n## Snapshots\n\n")
	sb.WriteString("| Time | Block | Tick | Fees | IL |\n")
	sb.WriteString("|------|-------|------|------|----|\n")

	for _, snap := range result.Snapshots {
		if len(result.Snapshots) <= 50 || snap.BlockNumber%10 == 0 {
			sb.WriteString(fmt.Sprintf("| %s | %d | %d | %s | %s |\n",
				snap.Timestamp.Format(time.RFC3339),
				snap.BlockNumber,
				snap.Tick,
				snap.CumulativeFees.String(),
				snap.IL.String()))
		}
	}

	if len(result.Snapshots) > 50 {
		sb.WriteString(fmt.Sprintf("\n_Showing 1 of %d snapshots (sampled)_\n", len(result.Snapshots)))
	}

	verdictPath := filepath.Join(dir, "verdict.md")
	return os.WriteFile(verdictPath, []byte(sb.String()), 0644)
}

// generatePnLSeries creates the pnl_series.csv file.
func generatePnLSeries(dir string, result *SimulationResult) error {
	var sb strings.Builder

	// Header
	sb.WriteString("timestamp,block_number,tick,price,liquidity,token0_amt,token1_amt,uncollected_fees,cumulative_fees,il,cumulative_il,net_pnl\n")

	for _, snap := range result.Snapshots {
		price := "0"
		if snap.Price != (domain.Decimal{}) {
			price = snap.Price.String()
		}

		liquidity := "0"
		if snap.Liquidity != (domain.Decimal{}) {
			liquidity = snap.Liquidity.String()
		}

		token0 := "0"
		if snap.Token0Amt != (domain.Decimal{}) {
			token0 = snap.Token0Amt.String()
		}

		token1 := "0"
		if snap.Token1Amt != (domain.Decimal{}) {
			token1 = snap.Token1Amt.String()
		}

		uncollFees := "0"
		if snap.UncollectedFees != (domain.Decimal{}) {
			uncollFees = snap.UncollectedFees.String()
		}

		cumFees := "0"
		if snap.CumulativeFees != (domain.Decimal{}) {
			cumFees = snap.CumulativeFees.String()
		}

		il := "0"
		if snap.IL != (domain.Decimal{}) {
			il = snap.IL.String()
		}

		// Cumulative IL (simplified)
		cumIL := il

		// Net PnL
		netPnL := snap.CumulativeFees.Add(snap.IL).String()

		sb.WriteString(fmt.Sprintf("%s,%d,%d,%s,%s,%s,%s,%s,%s,%s,%s,%s\n",
			snap.Timestamp.Format(time.RFC3339),
			snap.BlockNumber,
			snap.Tick,
			price,
			liquidity,
			token0,
			token1,
			uncollFees,
			cumFees,
			il,
			cumIL,
			netPnL))
	}

	pnlPath := filepath.Join(dir, "pnl_series.csv")
	return os.WriteFile(pnlPath, []byte(sb.String()), 0644)
}

// generateSummary creates the summary.json file.
func generateSummary(dir string, result *SimulationResult, comparison *ComparisonResult, pool domain.Pool) error {
	summary := map[string]interface{}{
		"version":            Version,
		"generated_at":        time.Now().Format(time.RFC3339),
		"pool": map[string]interface{}{
			"id":    pool.ID,
			"chain": pool.Chain,
		},
		"period": map[string]interface{}{
			"from": time.Unix(result.EntryBlockRef.TimeUnix, 0).Format(time.RFC3339),
			"to":   time.Unix(result.ExitBlockRef.TimeUnix, 0).Format(time.RFC3339),
		},
		"position": map[string]interface{}{
			"id":         result.Position.ID,
			"tick_lower": result.Position.TickLower,
			"tick_upper": result.Position.TickUpper,
			"amount_usd":  result.Position.AmountUSD.String(),
		},
		"metrics": map[string]interface{}{
			"simulated_fees":       result.SimulatedFees.String(),
			"ground_truth_fees":    comparison.GroundTruthFees.String(),
			"total_il":             result.TotalIL.String(),
			"net_pnl":              result.NetPnL.String(),
			"snapshots_count":      len(result.Snapshots),
			"error_pct":            comparison.ErrorPct,
		},
		"verdict": comparison.Verdict,
	}

	data, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal summary: %w", err)
	}

	summaryPath := filepath.Join(dir, "summary.json")
	return os.WriteFile(summaryPath, data, 0644)
}