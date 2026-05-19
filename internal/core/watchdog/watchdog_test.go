package watchdog

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestDefaultWatchdog_Run_Panics(t *testing.T) {
	w := NewDefaultWatchdog()

	require.Panics(t, func() {
		_ = w.Run(context.Background())
	}, "Run should panic as stub")
}

func TestDefaultWatchdog_Stop_Panics(t *testing.T) {
	w := NewDefaultWatchdog()

	require.Panics(t, func() {
		_ = w.Stop()
	}, "Stop should panic as stub")
}

func TestDefaultWatchdog_RunChecks_Panics(t *testing.T) {
	w := NewDefaultWatchdog()

	for _, interval := range []CheckInterval{CheckFast, CheckNormal, CheckSlow, CheckHealth} {
		t.Run(time.Duration(interval).String(), func(t *testing.T) {
			require.Panics(t, func() {
				_, _ = w.RunChecks(context.Background(), interval)
			}, "RunChecks should panic as stub")
		})
	}
}

func TestDefaultWatchdog_LastCheckTime_ReturnsEmptyMap(t *testing.T) {
	w := NewDefaultWatchdog()

	result := w.LastCheckTime()

	require.NotNil(t, result)
	require.Empty(t, result, "LastCheckTime should return empty map for stub")
}

func TestDefaultWatchdogConfig_DefaultValues(t *testing.T) {
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

func TestCheckResult_Fields(t *testing.T) {
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

func TestNewDefaultWatchdogWithConfig(t *testing.T) {
	cfg := WatchdogConfig{
		ExecutionStuckThreshold: 30 * time.Second,
		StopLossTimeout:         60 * time.Second,
		TotalExposureLimit:      50000,
		AlertOnPass:             true,
	}

	w := NewDefaultWatchdogWithConfig(cfg)
	require.NotNil(t, w)

	// Verify the config is stored by checking LastCheckTime works
	result := w.LastCheckTime()
	require.NotNil(t, result)
}

// Compile-time interface compliance check
var _ Watchdog = (*defaultWatchdog)(nil)