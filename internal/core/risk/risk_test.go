package risk_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

// TestAssessorNew verifies Assessor creation.
func TestAssessorNew(t *testing.T) {
	var a risk.Assessor = risk.New()
	require.NotNil(t, a)
}

// TestAssessorNewWithConfig verifies custom config.
func TestAssessorNewWithConfig(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.VaRWarnPct = decimal.NewFromFloat(0.10)
	var a risk.Assessor = risk.NewWithConfig(config)
	require.NotNil(t, a)
}

// TestRiskGateNew verifies RiskGate creation.
func TestRiskGateNew(t *testing.T) {
	g := risk.NewRiskGate(nil)
	require.NotNil(t, g)
}

// TestRiskGateNewWithConfig verifies custom config.
func TestRiskGateNewWithConfig(t *testing.T) {
	config := risk.DefaultRiskConfig()
	g := risk.NewRiskGateWithConfig(nil, config)
	require.NotNil(t, g)
}

// TestRiskGateGetState verifies state retrieval.
func TestRiskGateGetState(t *testing.T) {
	g := risk.NewRiskGate(nil)
	ctx := context.Background()

	state, err := g.GetState(ctx)
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelOK, state.Level)
}

// TestRiskGateCheckVaROK verifies OK VaR.
func TestRiskGateCheckVaROK(t *testing.T) {
	g := risk.NewRiskGate(nil)
	ctx := context.Background()

	level, err := g.CheckVaR(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(100))
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelOK, level)
}

// TestRiskGateCheckVaRWarn verifies VaR warning.
func TestRiskGateCheckVaRWarn(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.VaRWarnPct = decimal.NewFromFloat(0.05)
	g := risk.NewRiskGateWithConfig(nil, config)
	ctx := context.Background()

	level, err := g.CheckVaR(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(600))
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelWarn, level)
}

// TestRiskGateCheckVaRKill verifies VaR kill.
func TestRiskGateCheckVaRKill(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.VaRKillPct = decimal.NewFromFloat(0.10)
	g := risk.NewRiskGateWithConfig(nil, config)
	ctx := context.Background()

	level, err := g.CheckVaR(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(1200))
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelKill, level)
}

// TestRiskGateCheckDrawdownOK verifies OK drawdown.
func TestRiskGateCheckDrawdownOK(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.DailyDDKillPct = decimal.NewFromFloat(0.05) // 5%
	config.WeeklyDDFreezePct = decimal.NewFromFloat(0.10) // 10%
	g := risk.NewRiskGateWithConfig(nil, config)
	ctx := context.Background()

	// 2% drawdown - should be OK
	level, err := g.CheckDrawdown(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(9800), false)
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelOK, level)
}

// TestRiskGateCheckDrawdownKill verifies daily drawdown kill.
func TestRiskGateCheckDrawdownKill(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.DailyDDKillPct = decimal.NewFromFloat(0.05)
	g := risk.NewRiskGateWithConfig(nil, config)
	ctx := context.Background()

	level, err := g.CheckDrawdown(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(9400), false)
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelKill, level)
}

// TestRiskGateCheckDrawdownFreeze verifies weekly drawdown freeze.
func TestRiskGateCheckDrawdownFreeze(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.WeeklyDDFreezePct = decimal.NewFromFloat(0.10)
	g := risk.NewRiskGateWithConfig(nil, config)
	ctx := context.Background()

	level, err := g.CheckDrawdown(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(8900), true)
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelFreeze, level)
}

func TestRiskGateVaRRecoveryDoesNotClearWeeklyDrawdownFreeze(t *testing.T) {
	config := risk.DefaultRiskConfig()
	config.WeeklyDDFreezePct = decimal.NewFromFloat(0.10)
	g := risk.NewRiskGateWithConfig(nil, config)
	ctx := context.Background()

	level, err := g.CheckDrawdown(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(8900), true)
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelFreeze, level)

	level, err = g.CheckVaR(ctx, decimal.NewFromInt(10000), decimal.NewFromInt(100))
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelOK, level)

	state, err := g.GetState(ctx)
	require.NoError(t, err)
	require.Equal(t, ports.KillLevelFreeze, state.Level)
	require.Contains(t, state.Sources, ports.RiskSourceWeeklyDD)
}

// TestRiskGateIsBlocked verifies block check.
func TestRiskGateIsBlocked(t *testing.T) {
	g := risk.NewRiskGate(nil)
	ctx := context.Background()

	blocked, err := g.IsBlocked(ctx)
	require.NoError(t, err)
	require.False(t, blocked)
}

// TestDefaultRiskConfig verifies default config values.
func TestDefaultRiskConfig(t *testing.T) {
	config := risk.DefaultRiskConfig()
	require.True(t, config.VaRWarnPct.GreaterThan(decimal.Zero))
	require.True(t, config.VaRKillPct.GreaterThan(config.VaRWarnPct))
	require.True(t, config.DailyDDKillPct.GreaterThan(decimal.Zero))
	require.True(t, config.TotalExposurePct.GreaterThan(decimal.Zero))
}

// TestKillStateIsTerminal verifies terminal state check.
func TestKillStateIsTerminal(t *testing.T) {
	tests := []struct {
		level    ports.KillLevel
		terminal bool
	}{
		{ports.KillLevelOK, false},
		{ports.KillLevelWarn, false},
		{ports.KillLevelFreeze, false},
		{ports.KillLevelKill, true},
	}

	for _, tt := range tests {
		state := ports.KillState{Level: tt.level}
		require.Equal(t, tt.terminal, state.IsTerminal())
	}
}
