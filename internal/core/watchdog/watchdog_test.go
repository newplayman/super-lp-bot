package watchdog

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

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