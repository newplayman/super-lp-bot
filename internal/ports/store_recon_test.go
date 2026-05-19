package ports

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

// Compile-time interface compliance checks for ReconRepo
func TestReconRepoInterface(t *testing.T) {
	var _ ReconRepo = (*reconRepoNop)(nil)
}

// reconRepoNop is a no-op implementation for compile-time interface checks.
type reconRepoNop struct{}

func (reconRepoNop) AppendReconciliationLog(ctx context.Context, log ReconciliationLog) error { return nil }

func (reconRepoNop) ListReconciliationLogs(ctx context.Context, filter ReconLogFilter) ([]ReconciliationLog, error) {
	return nil, nil
}

func (reconRepoNop) GetLatestReconciliation(ctx context.Context, chain domain.ChainID) (ReconciliationLog, error) {
	return ReconciliationLog{}, nil
}

// Compile-time interface compliance checks for ReconStatus constants
func TestReconStatusConstants(t *testing.T) {
	if ReconPass != "pass" {
		t.Errorf("ReconPass = %q, want 'pass'", ReconPass)
	}
	if ReconFail != "fail" {
		t.Errorf("ReconFail = %q, want 'fail'", ReconFail)
	}
}

// TestReconResultFields verifies ReconResult struct has required fields
func TestReconResultFields(t *testing.T) {
	result := ReconResult{
		Chain:              domain.ChainBase,
		ExpectedCount:      5,
		ActualCount:        5,
		CountMatch:         true,
		ValueDeviationPct:  0.005, // 0.5%
		MismatchedPositions: []ReconMismatch{},
	}

	if result.Chain == "" {
		t.Error("ReconResult.Chain should not be empty")
	}
	if !result.CountMatch {
		t.Error("ReconResult.CountMatch should be true")
	}
	if result.ValueDeviationPct < 0 {
		t.Error("ReconResult.ValueDeviationPct should be non-negative")
	}
}

// TestReconMismatchFields verifies ReconMismatch struct has required fields
func TestReconMismatchFields(t *testing.T) {
	mismatch := ReconMismatch{
		PositionID:   "pos-123",
		PoolKey:      "base:uniswap_v3:0x456",
		OnChainUSD:   100.50,
		LocalUSD:     101.00,
		DeviationPct: 0.5,
	}

	if mismatch.PositionID == "" {
		t.Error("ReconMismatch.PositionID should not be empty")
	}
	if mismatch.PoolKey == "" {
		t.Error("ReconMismatch.PoolKey should not be empty")
	}
}

// TestReconciliationLogFields verifies ReconciliationLog struct has required fields
func TestReconciliationLogFields(t *testing.T) {
	log := ReconciliationLog{
		ID:      "log-123",
		Env:     domain.EnvLive,
		Chain:   domain.ChainBase,
		Status:  ReconPass,
		Result: ReconResult{Chain: domain.ChainBase, CountMatch: true},
		Message: "All positions reconciled successfully",
		Timestamp: 1234567890,
	}

	if log.ID == "" {
		t.Error("ReconciliationLog.ID should not be empty")
	}
	if log.Env == "" {
		t.Error("ReconciliationLog.Env should not be empty")
	}
	if log.Status == "" {
		t.Error("ReconciliationLog.Status should not be empty")
	}
}

// TestReconLogFilterFields verifies ReconLogFilter struct has required fields
func TestReconLogFilterFields(t *testing.T) {
	filter := ReconLogFilter{
		Env:    domain.EnvShadow,
		Chain:  domain.ChainSolana,
		Status: ReconPass,
		Since:  1234567890,
		Limit:  50,
	}

	if filter.Env != domain.EnvShadow {
		t.Errorf("ReconLogFilter.Env = %q, want 'shadow'", filter.Env)
	}
	if filter.Limit != 50 {
		t.Errorf("ReconLogFilter.Limit = %d, want 50", filter.Limit)
	}
}

// TestErrReconLogNotFound verifies error type
func TestErrReconLogNotFound(t *testing.T) {
	err := ErrReconLogNotFound
	if err.Error() != "reconciliation log not found" {
		t.Errorf("ErrReconLogNotFound.Error() = %q, want 'reconciliation log not found'", err.Error())
	}
	if !err.Is(ErrReconLogNotFound) {
		t.Error("ErrReconLogNotFound.Is should return true for itself")
	}
}
