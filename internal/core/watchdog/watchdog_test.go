package watchdog

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

type txRepoStub struct {
	stuck []domain.SignedTx
	err   error
}

func (t *txRepoStub) UpsertTx(context.Context, domain.SignedTx) error { return nil }
func (t *txRepoStub) GetTxByHash(context.Context, domain.ChainID, string) (domain.SignedTx, error) {
	return domain.SignedTx{}, nil
}
func (t *txRepoStub) ListTxsByStatus(context.Context, domain.ChainID, domain.TxStatus) ([]domain.SignedTx, error) {
	return nil, nil
}
func (t *txRepoStub) UpdateTxStatus(context.Context, domain.ChainID, string, domain.TxStatus, *domain.BlockRef) error {
	return nil
}
func (t *txRepoStub) ListPendingTxs(context.Context, domain.ChainID) ([]domain.SignedTx, error) {
	return nil, nil
}
func (t *txRepoStub) ListStuckTxs(context.Context, domain.ChainID, int64) ([]domain.SignedTx, error) {
	return t.stuck, t.err
}
func (t *txRepoStub) IncrementRFBAttempts(context.Context, domain.ChainID, string) error { return nil }
func (t *txRepoStub) GetRFBAttempts(context.Context, domain.ChainID, string) (int, error) {
	return 0, nil
}

func TestDefaultWatchdogNew(t *testing.T) {
	w := NewDefaultWatchdog()
	require.NotNil(t, w)
}

func TestDefaultWatchdogWithConfig(t *testing.T) {
	cfg := DefaultWatchdogConfig()
	cfg.ExecutionStuckThreshold = 30 * time.Second
	w := NewDefaultWatchdogWithConfig(cfg)
	require.NotNil(t, w)
}

func TestDefaultWatchdogWithRiskGate(t *testing.T) {
	rg := risk.NewRiskGate(nil)
	w := NewDefaultWatchdogWithRiskGate(rg)
	require.NotNil(t, w)

	// Verify riskGate is set by checking health check includes kill state
	ctx := context.Background()
	results, err := w.RunChecks(ctx, CheckHealth)
	require.NoError(t, err)
	require.NotEmpty(t, results)

	// Should have both system health and total exposure check
	foundTotalExposure := false
	for _, r := range results {
		if r.Type == CheckTypeTotalExposure {
			foundTotalExposure = true
			require.True(t, r.Passed) // KillLevelOK by default
		}
	}
	require.True(t, foundTotalExposure, "TotalExposure check should be present when RiskGate is set")
}

func TestDefaultWatchdogWithDependencies_StuckTxsFailInvariant(t *testing.T) {
	rg := risk.NewRiskGate(nil)
	w := NewDefaultWatchdogWithDependencies(rg, &txRepoStub{
		stuck: []domain.SignedTx{{Hash: "0xstuck"}},
	})

	results, err := w.RunChecks(context.Background(), CheckNormal)
	require.NoError(t, err)

	found := false
	for _, result := range results {
		if result.Type == CheckTypeExecutionStuck {
			found = true
			require.False(t, result.Passed)
			require.Contains(t, result.Reason, "stuck tx")
		}
	}
	require.True(t, found, "execution_stuck check should be present")
}

func TestDefaultWatchdogLastCheckTime(t *testing.T) {
	w := NewDefaultWatchdog()
	result := w.LastCheckTime()
	require.NotNil(t, result)
	require.Empty(t, result)
}

func TestDefaultWatchdogRunChecks(t *testing.T) {
	w := NewDefaultWatchdog()
	ctx := context.Background()

	// Test with CheckHealth interval
	results, err := w.RunChecks(ctx, CheckHealth)
	require.NoError(t, err)
	require.NotEmpty(t, results)
}

func TestDefaultWatchdogRunChecksNormal(t *testing.T) {
	w := NewDefaultWatchdog()
	ctx := context.Background()

	results, err := w.RunChecks(ctx, CheckNormal)
	require.NoError(t, err)
	require.NotEmpty(t, results)
}

func TestDefaultWatchdogRunChecksFast(t *testing.T) {
	w := NewDefaultWatchdog()
	ctx := context.Background()

	results, err := w.RunChecks(ctx, CheckFast)
	require.NoError(t, err)
	require.NotEmpty(t, results)
}

func TestDefaultWatchdogRunChecksSlow(t *testing.T) {
	w := NewDefaultWatchdog()
	ctx := context.Background()

	results, err := w.RunChecks(ctx, CheckSlow)
	require.NoError(t, err)
	require.NotEmpty(t, results)
}

func TestDefaultWatchdogRun(t *testing.T) {
	w := NewDefaultWatchdog()
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	go func() {
		_ = w.Run(ctx)
	}()

	// Give Run a moment to start
	time.Sleep(50 * time.Millisecond)
	err := w.Stop()
	require.NoError(t, err)
}

func TestDefaultWatchdogStop(t *testing.T) {
	w := NewDefaultWatchdog()
	err := w.Stop()
	require.NoError(t, err)
}

func TestDefaultWatchdogStopAfterRun(t *testing.T) {
	w := NewDefaultWatchdog()
	ctx := context.Background()

	go func() {
		w.Run(ctx)
	}()

	time.Sleep(100 * time.Millisecond)
	err := w.Stop()
	require.NoError(t, err)
}

func TestDefaultWatchdogConfig(t *testing.T) {
	cfg := DefaultWatchdogConfig()
	require.Equal(t, 60*time.Second, cfg.ExecutionStuckThreshold)
	require.Equal(t, 120*time.Second, cfg.StopLossTimeout)
	require.Equal(t, int64(100000), cfg.TotalExposureLimit)
	require.False(t, cfg.AlertOnPass)
}

func TestCheckIntervalConstants(t *testing.T) {
	require.Equal(t, 10*time.Second, time.Duration(CheckFast))
	require.Equal(t, 30*time.Second, time.Duration(CheckNormal))
	require.Equal(t, time.Minute, time.Duration(CheckSlow))
	require.Equal(t, 5*time.Minute, time.Duration(CheckHealth))
}

func TestCheckTypeConstants(t *testing.T) {
	require.Equal(t, CheckType("execution_stuck"), CheckTypeExecutionStuck)
	require.Equal(t, CheckType("rpc_connectivity"), CheckTypeRPCConnectivity)
	require.Equal(t, CheckType("pending_timeout"), CheckTypePendingTimeout)
	require.Equal(t, CheckType("total_exposure"), CheckTypeTotalExposure)
	require.Equal(t, CheckType("stop_loss_timed"), CheckTypeStopLossTimed)
	require.Equal(t, CheckType("system_health"), CheckTypeSystemHealth)
}

func TestCheckResultFields(t *testing.T) {
	ts := time.Now().Truncate(time.Second)
	result := CheckResult{
		Type:      CheckTypeExecutionStuck,
		Passed:    false,
		Level:     ports.AlertP1,
		Reason:    "execution stuck for 60s",
		Timestamp: ts,
		TraceID:   "test-trace-123",
	}

	require.Equal(t, CheckTypeExecutionStuck, result.Type)
	require.False(t, result.Passed)
	require.Equal(t, ports.AlertP1, result.Level)
	require.Equal(t, "execution stuck for 60s", result.Reason)
	require.Equal(t, ts, result.Timestamp)
	require.Equal(t, "test-trace-123", result.TraceID)
}

func TestCheckResultPassed(t *testing.T) {
	result := CheckResult{
		Type:      CheckTypeSystemHealth,
		Passed:    true,
		Level:     ports.AlertP2,
		Reason:    "OK",
		Timestamp: time.Now(),
	}

	require.True(t, result.Passed)
	require.Equal(t, ports.AlertP2, result.Level)
}

func TestWatchdogInterface(t *testing.T) {
	var w Watchdog = NewDefaultWatchdog()
	require.NotNil(t, w)
}

// Compile-time interface compliance check
var _ Watchdog = (*defaultWatchdog)(nil)
