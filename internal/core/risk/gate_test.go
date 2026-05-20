package risk

import (
	"context"
	"math"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// testCandidate is a test helper for Candidate
type testCandidate struct {
	NotionalUSD decimal.Decimal
}

func (c testCandidate) GetNotionalUSD() domain.Decimal {
	return c.NotionalUSD
}

// TestGate_NilSafe tests that a nil Gate returns false.
func TestGate_NilSafe(t *testing.T) {
	var g *RiskGate
	c := testCandidate{NotionalUSD: decimal.NewFromInt(10)}

	allowed, reason := g.Allow(c)
	if allowed {
		t.Error("nil Gate should not allow any candidate")
	}
	if reason != ReasonNilGate {
		t.Errorf("nil Gate should return ReasonNilGate, got %v", reason)
	}
}

// TestGate_DailyDDKill tests that -5.1% daily PnL blocks.
func TestGate_DailyDDKill(t *testing.T) {
	cfg := RiskConfig{
		DailyDDKillPct:    decimal.NewFromFloat(0.05),
		WeeklyDDFreezePct: decimal.NewFromFloat(0.10),
	}
	g := NewRiskGateWithConfig(nil, cfg)

	// Simulate daily DD: peak $100, current $94.9 = -5.1% drawdown
	g.peakUSD = decimal.NewFromInt(100)
	g.currentUSD = decimal.NewFromFloat(94.9)
	pnl := decimal.NewFromFloat(-5.1)
	g.lastPnL = &pnl

	c := testCandidate{NotionalUSD: decimal.NewFromInt(10)}
	allowed, reason := g.Allow(c)

	if allowed {
		t.Error("daily DD at -5.1% should block")
	}
	if reason != ReasonDailyDDKill {
		t.Errorf("expected ReasonDailyDDKill, got %v", reason)
	}
}

// TestGate_WeeklyDDFreeze tests that -10.1% weekly PnL blocks.
func TestGate_WeeklyDDFreeze(t *testing.T) {
	cfg := RiskConfig{
		DailyDDKillPct:    decimal.NewFromFloat(0.05),
		WeeklyDDFreezePct: decimal.NewFromFloat(0.10),
	}
	g := NewRiskGateWithConfig(nil, cfg)

	// Simulate weekly DD: peak $100, current $89.9 = -10.1% drawdown
	g.peakWeeklyUSD = decimal.NewFromInt(100)
	g.currentWeeklyUSD = decimal.NewFromFloat(89.9)
	pnl := decimal.NewFromFloat(-10.1)
	g.lastPnL = &pnl

	c := testCandidate{NotionalUSD: decimal.NewFromInt(10)}
	allowed, reason := g.Allow(c)

	if allowed {
		t.Error("weekly DD at -10.1% should block")
	}
	if reason != ReasonWeeklyDDFreeze {
		t.Errorf("expected ReasonWeeklyDDFreeze, got %v", reason)
	}
}

// TestGate_PnLNaN_FailClosed tests that nil PnL triggers fail-closed behavior.
// Since shopspring/decimal panics on NaN construction, we test the nil case
// as a proxy for invalid/uninitialized PnL state.
func TestGate_PnLNaN_FailClosed(t *testing.T) {
	cfg := DefaultRiskConfig()
	g := NewRiskGateWithConfig(nil, cfg)

	// Set nil PnL to simulate uninitialized/invalid state
	g.lastPnL = nil

	c := testCandidate{NotionalUSD: decimal.NewFromInt(10)}
	allowed, reason := g.Allow(c)

	if allowed {
		t.Error("nil PnL should block (fail-closed)")
	}
	if reason != ReasonPnLNaN {
		t.Errorf("expected ReasonPnLNaN, got %v", reason)
	}
}

// TestGate_OverSingleLimit tests that $51 exceeds $50 limit.
func TestGate_OverSingleLimit(t *testing.T) {
	cfg := RiskConfig{
		DailyDDKillPct:    decimal.NewFromFloat(0.05),
		WeeklyDDFreezePct: decimal.NewFromFloat(0.10),
		MaxSingleTradeUSD: decimal.NewFromInt(50),
	}
	g := NewRiskGateWithConfig(nil, cfg)

	// Set a valid PnL to avoid nil check blocking
	pnl := decimal.NewFromInt(100)
	g.lastPnL = &pnl

	c := testCandidate{NotionalUSD: decimal.NewFromInt(51)}
	allowed, reason := g.Allow(c)

	if allowed {
		t.Error("$51 over $50 limit should block")
	}
	if reason != ReasonOverSingleLimit {
		t.Errorf("expected ReasonOverSingleLimit, got %v", reason)
	}
}

// TestGate_HappyPath tests that healthy state allows.
func TestGate_HappyPath(t *testing.T) {
	cfg := RiskConfig{
		DailyDDKillPct:    decimal.NewFromFloat(0.05),
		WeeklyDDFreezePct: decimal.NewFromFloat(0.10),
		MaxSingleTradeUSD: decimal.NewFromInt(50),
	}
	g := NewRiskGateWithConfig(nil, cfg)

	// Healthy state: no significant drawdown
	g.peakUSD = decimal.NewFromInt(100)
	g.currentUSD = decimal.NewFromInt(100)
	g.peakWeeklyUSD = decimal.NewFromInt(100)
	g.currentWeeklyUSD = decimal.NewFromInt(100)
	pnl := decimal.NewFromInt(0)
	g.lastPnL = &pnl

	c := testCandidate{NotionalUSD: decimal.NewFromInt(30)}
	allowed, reason := g.Allow(c)

	if !allowed {
		t.Errorf("healthy state with $30 candidate should allow, got reason %v", reason)
	}
	if reason != ReasonOK {
		t.Errorf("expected ReasonOK, got %v", reason)
	}
}

// TestGate_ReasonsAreUnique tests that all RiskReason values are unique.
func TestGate_ReasonsAreUnique(t *testing.T) {
	reasons := []RiskReason{
		ReasonOK,
		ReasonNilGate,
		ReasonDailyDDKill,
		ReasonWeeklyDDFreeze,
		ReasonPnLNaN,
		ReasonOverSingleLimit,
		ReasonRepoError,
		ReasonInternalError,
	}

	seen := make(map[RiskReason]bool)
	for _, r := range reasons {
		if seen[r] {
			t.Errorf("duplicate RiskReason value: %v", r)
		}
		seen[r] = true
	}

	if len(seen) != len(reasons) {
		t.Errorf("expected %d unique reasons, got %d", len(reasons), len(seen))
	}
}

// TestGate_IsBlocked_BlocksAllow tests that blocked state gates the Allow method.
func TestGate_IsBlocked_BlocksAllow(t *testing.T) {
	cfg := DefaultRiskConfig()
	g := NewRiskGateWithConfig(nil, cfg)

	// Manually set blocked state
	g.state.Level = ports.KillLevelKill
	g.blockReason = ReasonManualKill

	c := testCandidate{NotionalUSD: decimal.NewFromInt(10)}
	allowed, reason := g.Allow(c)

	if allowed {
		t.Error("blocked Gate should not allow any candidate")
	}
	if reason != ReasonManualKill {
		t.Errorf("expected ReasonManualKill, got %v", reason)
	}
}

// TestGate_RepoError_FailClosed tests that repo errors return false.
func TestGate_RepoError_FailClosed(t *testing.T) {
	cfg := DefaultRiskConfig()
	mockRepo := &mockRiskRepo{err: context.DeadlineExceeded}
	g := NewRiskGateWithConfig(mockRepo, cfg)

	c := testCandidate{NotionalUSD: decimal.NewFromInt(10)}

	// When repo fails during GetState, should fail-closed
	allowed, reason := g.Allow(c)

	if allowed {
		t.Error("repo error should result in fail-closed (not allowed)")
	}
	if reason != ReasonRepoError {
		t.Errorf("expected ReasonRepoError, got %v", reason)
	}
}

// mockRiskRepo is a mock for testing repo errors.
type mockRiskRepo struct {
	err error
}

func (r *mockRiskRepo) AppendRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	return r.err
}

func (r *mockRiskRepo) ListRiskEvents(ctx context.Context, filter ports.RiskEventFilter) ([]ports.RiskEvent, error) {
	return nil, r.err
}

func (r *mockRiskRepo) GetKillState(ctx context.Context) (ports.KillState, error) {
	return ports.KillState{}, r.err
}

func (r *mockRiskRepo) UpsertKillState(ctx context.Context, state ports.KillState) error {
	return r.err
}

// Suppress unused import warning
var _ = math.NaN