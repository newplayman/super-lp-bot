// Package watchdog provides the global invariant monitoring for lp-bot.
package watchdog

import (
	"context"
	"fmt"
	"time"
)

// defaultWatchdog is the panic stub implementation of Watchdog.
// It panics on any method call to indicate the module is not yet implemented.
//
// This stub exists to establish the interface contract and allow
// compilation of dependent modules. Full implementation will come in
// Phase 1 (see spec §5.1).
type defaultWatchdog struct {
	config WatchdogConfig
}

// NewDefaultWatchdog creates a new panic stub watchdog with default config.
func NewDefaultWatchdog() Watchdog {
	return &defaultWatchdog{
		config: DefaultWatchdogConfig(),
	}
}

// NewDefaultWatchdogWithConfig creates a new panic stub watchdog with custom config.
func NewDefaultWatchdogWithConfig(cfg WatchdogConfig) Watchdog {
	return &defaultWatchdog{
		config: cfg,
	}
}

// Run implements Watchdog.
// Panics to indicate this is a scaffold stub.
func (w *defaultWatchdog) Run(ctx context.Context) error {
	panic("watchdog.Run: scaffold stub - not implemented")
}

// Stop implements Watchdog.
// Panics to indicate this is a scaffold stub.
func (w *defaultWatchdog) Stop() error {
	panic("watchdog.Stop: scaffold stub - not implemented")
}

// RunChecks implements Watchdog.
// Panics to indicate this is a scaffold stub.
func (w *defaultWatchdog) RunChecks(ctx context.Context, interval CheckInterval) ([]CheckResult, error) {
	panic(fmt.Sprintf("watchdog.RunChecks(%v): scaffold stub - not implemented", interval))
}

// LastCheckTime implements Watchdog.
// Returns an empty map to indicate no checks have run.
func (w *defaultWatchdog) LastCheckTime() map[CheckInterval]time.Time {
	return make(map[CheckInterval]time.Time)
}