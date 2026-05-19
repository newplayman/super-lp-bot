// Package main provides the lpbot-backtest CLI for Phase 0 validation.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"os"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// TestBacktestIntegration tests the full backtest flow with fixture data.
func TestBacktestIntegration(t *testing.T) {
	// Create test config
	cfg := &Config{
		Pool:      "0x1234567890123456789012345678901234567890",
		Chain:     "base",
		From:      time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC),
		To:        time.Date(2024, 1, 2, 0, 0, 0, 0, time.UTC),
		RangeMode: "symmetric",
		RangeK:    1.5,
		Tier:      "A",
		OutputDir: t.TempDir(),
	}

	// Create mock data loader
	loader := &MockLoader{
		swaps:       generateTestSwaps(cfg.Pool, cfg.From, cfg.To),
		poolStates:  generateTestPoolStates(cfg.Pool, cfg.From, cfg.To),
		groundTruth: decimal.NewFromFloat(100.50),
	}

	// Create mock ledger repo
	ledger := &MockLedgerRepo{}

	// Run backtest
	err := Run(context.Background(), cfg, loader, ledger)
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}

	// Verify output files exist
	checkOutputFiles(t, cfg.OutputDir)

	// Verify ledger entries
	if len(ledger.entries) == 0 {
		t.Error("Expected ledger entries but got none")
	}
}

// TestCompareResults tests the comparison logic.
func TestCompareResults(t *testing.T) {
	tests := []struct {
		name             string
		simulated        decimal.Decimal
		groundTruth      decimal.Decimal
		wantErrorPct     float64
		wantVerdict      string
	}{
		{
			name:         "exact match",
			simulated:    decimal.NewFromFloat(100.0),
			groundTruth:  decimal.NewFromFloat(100.0),
			wantErrorPct: 0.0,
			wantVerdict:  "PASS",
		},
		{
			name:         "within threshold",
			simulated:    decimal.NewFromFloat(102.0),
			groundTruth:  decimal.NewFromFloat(100.0),
			wantErrorPct: 2.0,
			wantVerdict:  "PASS",
		},
		{
			name:         "warning threshold",
			simulated:    decimal.NewFromFloat(107.0),
			groundTruth:  decimal.NewFromFloat(100.0),
			wantErrorPct: 7.0,
			wantVerdict:  "WARN",
		},
		{
			name:         "fail threshold",
			simulated:    decimal.NewFromFloat(120.0),
			groundTruth:  decimal.NewFromFloat(100.0),
			wantErrorPct: 20.0,
			wantVerdict:  "FAIL",
		},
		{
			name:         "both zero",
			simulated:    decimal.Zero,
			groundTruth:  decimal.Zero,
			wantErrorPct: 0.0,
			wantVerdict:  "PASS",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := Compare(tt.simulated, tt.groundTruth)
			if err != nil {
				t.Fatalf("Compare() error = %v", err)
			}

			// Use approximate comparison for floating point
			if math.Abs(result.ErrorPct-tt.wantErrorPct) > 0.01 {
				t.Errorf("ErrorPct = %v, want ~%v", result.ErrorPct, tt.wantErrorPct)
			}

			if result.Verdict != tt.wantVerdict {
				t.Errorf("Verdict = %v, want %v", result.Verdict, tt.wantVerdict)
			}
		})
	}
}

// TestSimulatorRangeMode tests different range modes.
func TestSimulatorRangeMode(t *testing.T) {
	pool := domain.Pool{
		ID:     "0xtestpool",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0x0000000000000000000000000000000000000001"),
		Token1: domain.MustParseAddress("0x0000000000000000000000000000000000000002"),
	}

	modes := []string{"symmetric", "increasing", "decreasing"}
	expectedTicks := []struct{ lower, upper int64 }{
		{-150, 150},
		{-75, 150},
		{-150, 75},
	}

	for i, mode := range modes {
		t.Run(mode, func(t *testing.T) {
			sim := NewSimulator(mode, 1.5)
			pos := sim.CreatePosition(pool, time.Now())

			// Check tick range is reasonable
			if pos.TickLower >= pos.TickUpper {
				t.Errorf("TickLower (%d) >= TickUpper (%d)", pos.TickLower, pos.TickUpper)
			}

			// Check spread matches expected
			spread := pos.TickUpper - pos.TickLower
			expectedSpread := expectedTicks[i].upper - expectedTicks[i].lower
			if spread != expectedSpread {
				// Allow some variance due to integer math
				if spread < expectedSpread-10 || spread > expectedSpread+10 {
					t.Errorf("Spread = %d, want approximately %d", spread, expectedSpread)
				}
			}
		})
	}
}

// TestOutputFiles tests output file generation.
func TestOutputFiles(t *testing.T) {
	outputDir := t.TempDir()

	result := &SimulationResult{
		Position: &domain.Position{
			ID:        "test_pos_1",
			TickLower: -1000,
			TickUpper: 1000,
			AmountUSD: decimal.NewFromFloat(5000),
		},
		SimulatedFees: decimal.NewFromFloat(150.25),
		TotalIL:       decimal.NewFromFloat(-50.0),
		NetPnL:        decimal.NewFromFloat(100.25),
		EntryBlockRef: domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   100000000,
			Hash:     "0xtest1",
			TimeUnix: time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC).Unix(),
		},
		ExitBlockRef: domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   100001000,
			Hash:     "0xtest2",
			TimeUnix: time.Date(2024, 1, 2, 0, 0, 0, 0, time.UTC).Unix(),
		},
		Snapshots: []PositionSnapshot{
			{
				Timestamp:       time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC),
				BlockNumber:     100000000,
				Tick:            0,
				Price:           decimal.NewFromFloat(3000.0),
				Liquidity:       decimal.NewFromFloat(1000000),
				Token0Amt:       decimal.NewFromFloat(1.0),
				Token1Amt:       decimal.NewFromFloat(3000.0),
				UncollectedFees: decimal.NewFromFloat(10.0),
				CumulativeFees:  decimal.NewFromFloat(50.0),
				IL:              decimal.NewFromFloat(-10.0),
			},
		},
	}

	comparison := &ComparisonResult{
		SimulatedFees:   decimal.NewFromFloat(150.25),
		GroundTruthFees: decimal.NewFromFloat(155.00),
		ErrorPct:         3.06,
		Verdict:         "PASS",
	}

	pool := domain.Pool{
		ID:    "0xtestpool",
		Chain: domain.ChainBase,
	}

	err := GenerateOutputs(outputDir, result, comparison, pool)
	if err != nil {
		t.Fatalf("GenerateOutputs() error = %v", err)
	}

	// Check all files exist
	checkOutputFiles(t, outputDir)

	// Verify verdict.md content
	verdictPath := outputDir + "/verdict.md"
	content, err := os.ReadFile(verdictPath)
	if err != nil {
		t.Fatalf("Read verdict.md: %v", err)
	}

	if len(content) == 0 {
		t.Error("verdict.md is empty")
	}

	// Verify pnl_series.csv content
	csvPath := outputDir + "/pnl_series.csv"
	csvContent, err := os.ReadFile(csvPath)
	if err != nil {
		t.Fatalf("Read pnl_series.csv: %v", err)
	}

	if len(csvContent) == 0 {
		t.Error("pnl_series.csv is empty")
	}

	// Verify summary.json is valid JSON
	summaryPath := outputDir + "/summary.json"
	summaryContent, err := os.ReadFile(summaryPath)
	if err != nil {
		t.Fatalf("Read summary.json: %v", err)
	}

	var summary map[string]interface{}
	if err := json.Unmarshal(summaryContent, &summary); err != nil {
		t.Fatalf("Parse summary.json: %v", err)
	}

	if summary["verdict"] != "PASS" {
		t.Errorf("summary verdict = %v, want PASS", summary["verdict"])
	}
}

// checkOutputFiles verifies that all expected output files exist.
func checkOutputFiles(t *testing.T, dir string) {
	files := []string{"verdict.md", "pnl_series.csv", "summary.json"}

	for _, f := range files {
		path := dir + "/" + f
		if _, err := os.Stat(path); os.IsNotExist(err) {
			t.Errorf("Expected output file %s does not exist", f)
		}
	}
}

// Mock implementations for testing

type MockLoader struct {
	swaps       []ports.Swap
	poolStates  []domain.PoolState
	groundTruth domain.Decimal
}

func (m *MockLoader) LoadSwaps(ctx context.Context, pool domain.Pool, from, to time.Time) ([]ports.Swap, error) {
	return m.swaps, nil
}

func (m *MockLoader) LoadPoolStates(ctx context.Context, pool domain.Pool, from, to time.Time, step time.Duration) ([]domain.PoolState, error) {
	return m.poolStates, nil
}

func (m *MockLoader) LoadCollectedFees(ctx context.Context, pool domain.Pool, from, to time.Time) (domain.Decimal, error) {
	return m.groundTruth, nil
}

type MockLedgerRepo struct {
	entries []ports.LedgerEntry
}

func (m *MockLedgerRepo) Append(ctx context.Context, entry ports.LedgerEntry) (ports.LedgerEntry, error) {
	m.entries = append(m.entries, entry)
	return entry, nil
}

func (m *MockLedgerRepo) ByPosition(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	return m.entries, nil
}

func (m *MockLedgerRepo) ByPositionAndKind(ctx context.Context, positionID string, kind ports.LedgerEntryKind) ([]ports.LedgerEntry, error) {
	var result []ports.LedgerEntry
	for _, e := range m.entries {
		if e.Kind == kind {
			result = append(result, e)
		}
	}
	return result, nil
}

func (m *MockLedgerRepo) AggregateByKind(ctx context.Context, positionID string) (map[ports.LedgerEntryKind]domain.Decimal, error) {
	result := make(map[ports.LedgerEntryKind]domain.Decimal)
	for _, e := range m.entries {
		result[e.Kind] = result[e.Kind].Add(e.Amount)
	}
	return result, nil
}

func (m *MockLedgerRepo) LatestBlock(ctx context.Context) (*domain.BlockRef, error) {
	return nil, nil
}

// Test helper functions

func generateTestSwaps(poolID string, from, to time.Time) []ports.Swap {
	var swaps []ports.Swap

	current := from
	blockNum := uint64(100000000)

	for current.Before(to) {
		swap := ports.Swap{
			ID:          "swap_test",
			PoolID:      poolID,
			Chain:       domain.ChainBase,
			Timestamp:   current,
			BlockNumber: blockNum,
			Amount0:     decimal.NewFromFloat(1.0),
			Amount1:     decimal.NewFromFloat(3000.0),
			Tick:        0,
			SqrtPriceX96: decimal.NewFromInt(1 << 32),
		}

		swaps = append(swaps, swap)
		current = current.Add(5 * time.Minute)
		blockNum++
	}

	return swaps
}

func generateTestPoolStates(poolID string, from, to time.Time) []domain.PoolState {
	var states []domain.PoolState

	current := from
	blockNum := uint64(100000000)

	for current.Before(to) {
		state := domain.PoolState{
			BlockRef: domain.BlockRef{
				Chain:    domain.ChainBase,
				Number:   blockNum,
				Hash:     fmt.Sprintf("0x%x", blockNum),
				TimeUnix: current.Unix(),
			},
			Tick:      0,
			Liquidity: big.NewInt(1000000),
		}

		states = append(states, state)
		current = current.Add(1 * time.Hour)
		blockNum++
	}

	return states
}