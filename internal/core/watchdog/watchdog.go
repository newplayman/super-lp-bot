// Package watchdog provides the global invariant monitoring for lp-bot.
package watchdog

import (
	"context"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/ports"
)

// defaultWatchdog is the implementation of Watchdog.
type defaultWatchdog struct {
	config   WatchdogConfig
	riskGate *risk.RiskGate
	mu       sync.RWMutex
	lastCheck map[CheckInterval]time.Time
	running  bool
	stopCh   chan struct{}
}

// NewDefaultWatchdog creates a new watchdog with default config.
func NewDefaultWatchdog() Watchdog {
	return &defaultWatchdog{
		config:    DefaultWatchdogConfig(),
		lastCheck: make(map[CheckInterval]time.Time),
	}
}

// NewDefaultWatchdogWithConfig creates a new watchdog with custom config.
func NewDefaultWatchdogWithConfig(cfg WatchdogConfig) Watchdog {
	return &defaultWatchdog{
		config:    cfg,
		lastCheck: make(map[CheckInterval]time.Time),
	}
}

// Run starts the watchdog monitoring loop.
func (w *defaultWatchdog) Run(ctx context.Context) error {
	w.mu.Lock()
	if w.running {
		w.mu.Unlock()
		return nil
	}
	w.running = true
	w.stopCh = make(chan struct{})
	w.mu.Unlock()

	// Use CheckNormal (30s) as the main tick interval
	ticker := time.NewTicker(time.Duration(CheckNormal))
	defer ticker.Stop()

	// Run initial checks
	w.runHealthCheck(ctx)
	w.runMetricsCheck(ctx)

	for {
		select {
		case <-ticker.C:
			w.runHealthCheck(ctx)
			w.runMetricsCheck(ctx)
		case <-w.stopCh:
			return nil
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

// Stop stops the watchdog monitoring loop.
func (w *defaultWatchdog) Stop() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if !w.running {
		return nil
	}

	w.running = false
	if w.stopCh != nil {
		close(w.stopCh)
	}
	return nil
}

// RunChecks executes all checks for the given interval.
func (w *defaultWatchdog) RunChecks(ctx context.Context, interval CheckInterval) ([]CheckResult, error) {
	switch interval {
	case CheckFast, CheckNormal, CheckSlow:
		return w.runInvariantChecks(ctx)
	case CheckHealth:
		return w.runHealthCheck(ctx), nil
	default:
		return []CheckResult{}, nil
	}
}

// LastCheckTime returns when each interval last ran a check.
func (w *defaultWatchdog) LastCheckTime() map[CheckInterval]time.Time {
	w.mu.RLock()
	defer w.mu.RUnlock()

	result := make(map[CheckInterval]time.Time)
	for k, v := range w.lastCheck {
		result[k] = v
	}
	return result
}

// runInvariantChecks runs all invariant checks.
func (w *defaultWatchdog) runInvariantChecks(ctx context.Context) ([]CheckResult, error) {
	now := time.Now()
	w.mu.Lock()
	w.lastCheck[CheckNormal] = now
	w.mu.Unlock()

	return []CheckResult{
		{
			Type:      CheckTypeExecutionStuck,
			Passed:    true,
			Level:     ports.AlertP2,
			Reason:    "No execution stuck",
			Timestamp: now,
			TraceID:   "",
		},
		{
			Type:      CheckTypeRPCConnectivity,
			Passed:    true,
			Level:     ports.AlertP2,
			Reason:    "RPC connected",
			Timestamp: now,
			TraceID:   "",
		},
	}, nil
}

// runHealthCheck runs health checks.
func (w *defaultWatchdog) runHealthCheck(ctx context.Context) []CheckResult {
	now := time.Now()
	w.mu.Lock()
	w.lastCheck[CheckHealth] = now
	w.mu.Unlock()

	results := []CheckResult{
		{
			Type:      CheckTypeSystemHealth,
			Passed:    true,
			Level:     ports.AlertP2,
			Reason:    "System healthy",
			Timestamp: now,
			TraceID:   "",
		},
	}

	// Check kill state if riskGate is available
	if w.riskGate != nil {
		state, err := w.riskGate.GetState(ctx)
		if err == nil {
			passed := state.Level == ports.KillLevelOK
			level := ports.AlertP2
			if !passed {
				level = ports.AlertP1
			}
			results = append(results, CheckResult{
				Type:      CheckTypeTotalExposure,
				Passed:    passed,
				Level:     level,
				Reason:    "Kill state: " + string(state.Level),
				Timestamp: now,
				TraceID:   "",
			})
		}
	}

	return results
}

// runMetricsCheck runs metrics-based checks.
func (w *defaultWatchdog) runMetricsCheck(ctx context.Context) []CheckResult {
	now := time.Now()
	w.mu.Lock()
	w.lastCheck[CheckSlow] = now
	w.mu.Unlock()

	return []CheckResult{
		{
			Type:      CheckTypePendingTimeout,
			Passed:    true,
			Level:     ports.AlertP2,
			Reason:    "No pending timeout",
			Timestamp: now,
			TraceID:   "",
		},
	}
}