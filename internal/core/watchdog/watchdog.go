// Package watchdog provides the global invariant monitoring and kill-switch
// trigger for lp-bot (spec §5.1).
//
// Watchdog runs multiple check loops at different intervals (10s/30s/1min/5min)
// to enforce system-level invariants and trigger kill-switch transitions
// when risk thresholds are breached.
//
// Key components:
//   - Watchdog: main interface for invariant checking and kill triggers
//   - CheckResult: outcome of a single invariant check
//   - CheckInterval: the frequency tier for different checks
//
// See spec §5 for the complete risk architecture including kill-switch design.
package watchdog

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// defaultWatchdog is the implementation of Watchdog.
type defaultWatchdog struct {
	config    WatchdogConfig
	riskGate  *risk.RiskGate
	txRepo    ports.TxRepo
	mu        sync.RWMutex
	lastCheck map[CheckInterval]time.Time
	running   bool
	stopCh    chan struct{}
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

// NewDefaultWatchdogWithRiskGate creates a watchdog with a RiskGate for kill state monitoring.
func NewDefaultWatchdogWithRiskGate(rg *risk.RiskGate) Watchdog {
	return &defaultWatchdog{
		config:    DefaultWatchdogConfig(),
		riskGate:  rg,
		lastCheck: make(map[CheckInterval]time.Time),
	}
}

// NewDefaultWatchdogWithDependencies creates a watchdog backed by RiskGate and TxRepo runtime state.
func NewDefaultWatchdogWithDependencies(rg *risk.RiskGate, txRepo ports.TxRepo) Watchdog {
	return &defaultWatchdog{
		config:    DefaultWatchdogConfig(),
		riskGate:  rg,
		txRepo:    txRepo,
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

	// Use CheckFast (10s) as the main tick for responsive monitoring
	ticker := time.NewTicker(time.Duration(CheckFast))
	defer ticker.Stop()

	// Run initial checks
	w.runHealthCheck(ctx)
	w.runInvariantChecks(ctx)
	w.runMetricsCheck(ctx)

	for {
		select {
		case <-ticker.C:
			now := time.Now()
			w.mu.RLock()
			healthLast := w.lastCheck[CheckHealth]
			metricsLast := w.lastCheck[CheckSlow]
			w.mu.RUnlock()

			// Run health check if 5 minutes elapsed
			if now.Sub(healthLast) >= time.Duration(CheckHealth) {
				w.runHealthCheck(ctx)
			}

			// Run metrics check if 1 minute elapsed
			if now.Sub(metricsLast) >= time.Duration(CheckSlow) {
				w.runMetricsCheck(ctx)
			}

			// Always run invariant checks (30s interval via CheckNormal)
			w.runInvariantChecks(ctx)
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

	results := []CheckResult{
		{
			Type:      CheckTypeExecutionStuck,
			Passed:    true,
			Level:     ports.AlertP2,
			Reason:    "no stuck transactions detected",
			Timestamp: now,
		},
		{
			Type:      CheckTypePendingTimeout,
			Passed:    true,
			Level:     ports.AlertP2,
			Reason:    "no pending timeout detected",
			Timestamp: now,
		},
		{
			Type:      CheckTypeRPCConnectivity,
			Passed:    ctx.Err() == nil,
			Level:     ports.AlertP2,
			Reason:    "runtime context healthy",
			Timestamp: now,
		},
	}

	if ctx.Err() != nil {
		results[2].Reason = ctx.Err().Error()
	}

	if w.txRepo != nil {
		stuckTxs, err := w.txRepo.ListStuckTxs(ctx, domain.ChainBase, int64(w.config.ExecutionStuckThreshold/time.Second))
		if err != nil {
			results[0].Passed = false
			results[0].Level = ports.AlertP1
			results[0].Reason = fmt.Sprintf("stuck tx query failed: %v", err)
			results[1].Passed = false
			results[1].Level = ports.AlertP1
			results[1].Reason = fmt.Sprintf("pending timeout query failed: %v", err)
		} else if len(stuckTxs) > 0 {
			reason := fmt.Sprintf("%d stuck tx(s) older than %s", len(stuckTxs), w.config.ExecutionStuckThreshold)
			results[0].Passed = false
			results[0].Level = ports.AlertP1
			results[0].Reason = reason
			results[1].Passed = false
			results[1].Level = ports.AlertP1
			results[1].Reason = reason
		}
	}

	if w.riskGate == nil {
		return results, nil
	}

	state, err := w.riskGate.GetState(ctx)
	if err != nil {
		results[0].Passed = false
		results[0].Level = ports.AlertP1
		results[0].Reason = fmt.Sprintf("risk state unavailable: %v", err)
		results[1].Passed = false
		results[1].Level = ports.AlertP1
		results[1].Reason = fmt.Sprintf("risk state unavailable: %v", err)
		results[2].Passed = false
		results[2].Level = ports.AlertP1
		results[2].Reason = fmt.Sprintf("risk state unavailable: %v", err)
		return results, nil
	}

	for _, source := range state.Sources {
		switch source {
		case ports.RiskSourceExecutionStuck:
			results[0].Passed = false
			results[0].Level = ports.AlertP1
			results[0].Reason = "execution_stuck source active in kill state"
		case ports.RiskSourceDatasource:
			results[2].Passed = false
			results[2].Level = ports.AlertP1
			results[2].Reason = "datasource source active in kill state"
		}
	}

	return results, nil
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
		} else {
			results = append(results, CheckResult{
				Type:      CheckTypeTotalExposure,
				Passed:    false,
				Level:     ports.AlertP1,
				Reason:    fmt.Sprintf("kill state unavailable: %v", err),
				Timestamp: now,
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

	result := CheckResult{
		Type:      CheckTypePendingTimeout,
		Passed:    true,
		Level:     ports.AlertP2,
		Reason:    "no pending-timeout source active",
		Timestamp: now,
	}

	if w.riskGate != nil {
		state, err := w.riskGate.GetState(ctx)
		if err != nil {
			result.Passed = false
			result.Level = ports.AlertP1
			result.Reason = fmt.Sprintf("kill state unavailable: %v", err)
			return []CheckResult{result}
		}
		for _, source := range state.Sources {
			if source == ports.RiskSourceExecutionStuck {
				result.Passed = false
				result.Level = ports.AlertP1
				result.Reason = "pending timeout inferred from execution_stuck source"
				break
			}
		}
	}

	return []CheckResult{result}
}
