package ports

import (
	"context"
	"testing"
	"time"
)

// Compile-time interface compliance checks for RiskRepo
func TestRiskRepoInterface(t *testing.T) {
	var _ RiskRepo = (*riskRepoNop)(nil)
}

// riskRepoNop is a no-op implementation for compile-time interface checks.
type riskRepoNop struct{}

func (riskRepoNop) AppendRiskEvent(ctx context.Context, event RiskEvent) error { return nil }

func (riskRepoNop) ListRiskEvents(ctx context.Context, filter RiskEventFilter) ([]RiskEvent, error) {
	return nil, nil
}

func (riskRepoNop) GetKillState(ctx context.Context) (KillState, error) {
	return KillState{}, nil
}

func (riskRepoNop) UpsertKillState(ctx context.Context, state KillState) error { return nil }

// Compile-time interface compliance checks for KillState types
func TestKillLevelConstants(t *testing.T) {
	// Verify kill level constants are defined correctly
	if KillLevelOK != "ok" {
		t.Errorf("KillLevelOK = %q, want 'ok'", KillLevelOK)
	}
	if KillLevelWarn != "warn" {
		t.Errorf("KillLevelWarn = %q, want 'warn'", KillLevelWarn)
	}
	if KillLevelFreeze != "freeze" {
		t.Errorf("KillLevelFreeze = %q, want 'freeze'", KillLevelFreeze)
	}
	if KillLevelKill != "kill" {
		t.Errorf("KillLevelKill = %q, want 'kill'", KillLevelKill)
	}
}

func TestRiskSourceConstants(t *testing.T) {
	// Verify risk source constants are defined correctly
	sources := []RiskSource{
		RiskSourceDailyDD,
		RiskSourceWeeklyDD,
		RiskSourceVaR,
		RiskSourceManual,
		RiskSourceRecon,
		RiskSourceDatasource,
		RiskSourceExecutionStuck,
	}
	for _, src := range sources {
		if src == "" {
			t.Error("RiskSource constant is empty")
		}
	}
}

func TestRiskActionConstants(t *testing.T) {
	// Verify risk action constants are defined correctly
	actions := []RiskAction{
		RiskActionReject,
		RiskActionFreeze,
		RiskActionStopLoss,
		RiskActionRaiseKill,
		RiskActionLowerWarn,
		RiskActionRebalance,
		RiskActionTightenRange,
	}
	for _, act := range actions {
		if act == "" {
			t.Error("RiskAction constant is empty")
		}
	}
}

// TestKillStateIsTerminal verifies IsTerminal logic
func TestKillStateIsTerminal(t *testing.T) {
	tests := []struct {
		level KillLevel
		want  bool
	}{
		{KillLevelOK, false},
		{KillLevelWarn, false},
		{KillLevelFreeze, false},
		{KillLevelKill, true},
	}

	for _, tt := range tests {
		t.Run(string(tt.level), func(t *testing.T) {
			state := KillState{Level: tt.level}
			if got := state.IsTerminal(); got != tt.want {
				t.Errorf("KillState.IsTerminal() = %v, want %v", got, tt.want)
			}
		})
	}
}

// TestRiskEventFields verifies RiskEvent struct has required fields
func TestRiskEventFields(t *testing.T) {
	event := RiskEvent{
		ID:         "test-id",
		PositionID: "position-123",
		PoolKey:    "base:uniswap_v3:0x123",
		Source:    RiskSourceDailyDD,
		Action:    RiskActionReject,
		Level:     KillLevelWarn,
		Details:   "test details",
		Timestamp: time.Now().Unix(),
	}

	if event.ID == "" {
		t.Error("RiskEvent.ID should not be empty")
	}
	if event.Source == "" {
		t.Error("RiskEvent.Source should not be empty")
	}
	if event.Action == "" {
		t.Error("RiskEvent.Action should not be empty")
	}
}

// TestRiskEventFilterFields verifies RiskEventFilter struct has required fields
func TestRiskEventFilterFields(t *testing.T) {
	filter := RiskEventFilter{
		PoolKey:    "base:uniswap_v3:0x123",
		PositionID: "position-123",
		Source:     RiskSourceVaR,
		Since:      1234567890,
		Limit:      100,
	}

	if filter.Limit != 100 {
		t.Errorf("RiskEventFilter.Limit = %d, want 100", filter.Limit)
	}
}

// TestErrRiskEventNotFound verifies error type
func TestErrRiskEventNotFound(t *testing.T) {
	err := ErrRiskEventNotFound
	if err.Error() != "risk event not found" {
		t.Errorf("ErrRiskEventNotFound.Error() = %q, want 'risk event not found'", err.Error())
	}
	if !err.Is(ErrRiskEventNotFound) {
		t.Error("ErrRiskEventNotFound.Is should return true for itself")
	}
}
