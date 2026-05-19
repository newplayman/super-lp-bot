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
	"time"

	"github.com/lpbot/lpbot/internal/ports"
)

// CheckInterval represents the frequency tier for watchdog checks.
type CheckInterval time.Duration

const (
	// CheckFast runs every 10 seconds for critical checks.
	CheckFast CheckInterval = CheckInterval(10 * time.Second)
	// CheckNormal runs every 30 seconds for standard checks.
	CheckNormal CheckInterval = CheckInterval(30 * time.Second)
	// CheckSlow runs every 1 minute for comprehensive checks.
	CheckSlow CheckInterval = CheckInterval(time.Minute)
	// CheckHealth runs every 5 minutes for system health checks.
	CheckHealth CheckInterval = CheckInterval(5 * time.Minute)
)

// CheckType identifies the type of invariant check performed.
type CheckType string

const (
	CheckTypeExecutionStuck  CheckType = "execution_stuck"
	CheckTypeRPCConnectivity  CheckType = "rpc_connectivity"
	CheckTypePendingTimeout   CheckType = "pending_timeout"
	CheckTypeTotalExposure    CheckType = "total_exposure"
	CheckTypeStopLossTimed   CheckType = "stop_loss_timed"
	CheckTypeSystemHealth     CheckType = "system_health"
)

// CheckResult represents the outcome of a watchdog check.
type CheckResult struct {
	Type      CheckType   // which check was performed
	Passed    bool        // true if invariant held
	Level     ports.AlertLevel // alert level if failed
	Reason    string      // human-readable explanation
	Timestamp time.Time   // when the check ran
	TraceID   string      // correlation ID for this check
}

// Watchdog defines the interface for global invariant monitoring (spec §5.1).
//
// Watchdog is responsible for:
//   - Multi-interval loop scheduling (10s/30s/1min/5min)
//   - Invariant runtime assertion
//   - Kill state escalation via RiskGate
//   - Alert dispatch via Alerter
//
// Thread safety: implementations must be safe for concurrent use.
type Watchdog interface {
	// Run starts the watchdog monitoring loops.
	// It blocks until the context is cancelled or Stop is called.
	// Returns error only if the loops cannot be started.
	Run(ctx context.Context) error

	// Stop halts all monitoring loops gracefully.
	// In-flight checks will complete before returning.
	Stop() error

	// RunChecks executes all checks for the given interval immediately.
	// This is used for manual triggers or testing.
	// Returns all check results from this run.
	RunChecks(ctx context.Context, interval CheckInterval) ([]CheckResult, error)

	// LastCheckTime returns when each interval last ran a check.
	LastCheckTime() map[CheckInterval]time.Time
}

// WatchdogConfig contains configuration for watchdog behavior.
type WatchdogConfig struct {
	// ExecutionStuckThreshold is how long a pending tx must be stuck
	// before triggering a warning (default: 60 seconds).
	ExecutionStuckThreshold time.Duration

	// StopLossTimeout is the max time allowed between stop_loss trigger
	// and actual exit tx (default: 120 seconds).
	StopLossTimeout time.Duration

	// TotalExposureLimit is the max total position value in USD cents.
	TotalExposureLimit int64

	// AlertOnPass enables alerting even when checks pass (for monitoring).
	AlertOnPass bool
}

// DefaultWatchdogConfig returns the default configuration values.
func DefaultWatchdogConfig() WatchdogConfig {
	return WatchdogConfig{
		ExecutionStuckThreshold: 60 * time.Second,
		StopLossTimeout:         120 * time.Second,
		TotalExposureLimit:     100000, // $1000 default
		AlertOnPass:             false,
	}
}

// Compile-time interface compliance check
var _ Watchdog = (*defaultWatchdog)(nil)