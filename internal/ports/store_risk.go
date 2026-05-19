// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// The Store interfaces provide data persistence for domain aggregates.
// Each repository is scoped to a single aggregate type to maintain
// clear boundaries and separation of concerns.
//
// Repository design principles (from spec §4.4):
//   - Aggregate-scoped: PoolRepo, PositionRepo, TxRepo, etc.
//   - sqlc generates query code for two SQL backends (sqlite/postgres)
//   - Handwritten SQL prioritized for audit readability
//   - All monetary values stored as TEXT (decimal strings), never float
package ports

import (
	"context"
	"time"
)

// KillLevel represents the severity level of the kill switch.
type KillLevel string

const (
	KillLevelOK     KillLevel = "ok"
	KillLevelWarn   KillLevel = "warn"
	KillLevelFreeze KillLevel = "freeze"
	KillLevelKill   KillLevel = "kill"
)

// RiskSource identifies the source that triggered a risk event.
type RiskSource string

const (
	RiskSourceDailyDD        RiskSource = "daily_dd"
	RiskSourceWeeklyDD       RiskSource = "weekly_dd"
	RiskSourceVaR            RiskSource = "var"
	RiskSourceManual         RiskSource = "manual"
	RiskSourceRecon          RiskSource = "recon"
	RiskSourceDatasource     RiskSource = "datasource"
	RiskSourceExecutionStuck RiskSource = "execution_stuck"
)

// RiskAction represents the action taken in response to a risk event.
type RiskAction string

const (
	RiskActionReject      RiskAction = "reject"
	RiskActionFreeze      RiskAction = "freeze"
	RiskActionStopLoss    RiskAction = "stop_loss"
	RiskActionRaiseKill   RiskAction = "raise_kill"
	RiskActionLowerWarn   RiskAction = "lower_warn"
	RiskActionRebalance   RiskAction = "rebalance"
	RiskActionTightenRange RiskAction = "tighten_range"
)

// KillState represents the current kill switch state (spec §5.2).
//
// The kill switch has four levels: ok, warn, freeze, kill.
// Transitions:
//   - ok → warn: risk threshold breached
//   - warn → freeze: prolonged risk exposure
//   - freeze → ok: conditions cleared automatically
//   - kill → ok: requires manual unlock via lpbot-cli
type KillState struct {
	Level    KillLevel   // current kill level
	Sources  []RiskSource // sources that triggered the current level
	Since    time.Time   // when the current level was entered
	Reason   string      // human-readable reason for the current level
	Unlocker string      // who unlocked (empty for auto-clear from freeze)
}

// IsTerminal returns true if this kill level requires manual intervention.
func (s KillState) IsTerminal() bool {
	return s.Level == KillLevelKill
}

// RiskEvent represents a single risk event record (spec §4.2).
//
// risk_events table records single-pool and portfolio-level risk triggers.
// This is an append-only table for audit trail.
type RiskEvent struct {
	ID        string      // unique event ID (UUID v7)
	PositionID string     // associated position (empty for portfolio events)
	PoolKey   string      // "{chain}:{protocol}:{id}" for pool events
	Source    RiskSource  // what triggered this event
	Action    RiskAction  // what action was taken
	Level     KillLevel   // kill level at time of event
	Details   string      // human-readable details
	Timestamp int64       // unix timestamp
}

// RiskRepo defines the repository interface for risk aggregate persistence.
//
// RiskRepo handles:
//   - risk_events table: single-pool and portfolio risk trigger records (append)
//   - kill_switch_state table: current kill state (single row, UPSERT)
//
// The repository is designed for:
//   - Risk module recording trigger events
//   - Watchdog monitoring kill state
//   - Audit trail for risk decisions
//
// Implementations must be safe for concurrent use.
type RiskRepo interface {
	// AppendRiskEvent appends a new risk event to the audit trail.
	//
	// This operation writes to the risk_events table.
	// Events are immutable once written (append-only).
	//
	// Returns error if ctx is cancelled or context deadline exceeded.
	AppendRiskEvent(ctx context.Context, event RiskEvent) error

	// ListRiskEvents returns risk events matching the provided filters.
	//
	// If poolKey is non-empty, filters to that specific pool.
	// If positionID is non-empty, filters to that specific position.
	// If source is non-empty, filters to that risk source.
	// If limit > 0, returns at most limit events (ordered by Timestamp DESC).
	//
	// Returns empty slice if no matches (not error).
	ListRiskEvents(ctx context.Context, filter RiskEventFilter) ([]RiskEvent, error)

	// GetKillState retrieves the current kill switch state.
	//
	// Returns the current state (defaults to KillLevelOK if never set).
	// Returns error if ctx is cancelled or context deadline exceeded.
	GetKillState(ctx context.Context) (KillState, error)

	// UpsertKillState updates the kill switch state.
	//
	// This operation writes to the kill_switch_state table (single row UPSERT).
	// Use RaiseKill/LowerWarn from RiskGate for controlled transitions.
	//
	// Returns error if ctx is cancelled or context deadline exceeded.
	UpsertKillState(ctx context.Context, state KillState) error
}

// RiskEventFilter specifies criteria for filtering risk events.
type RiskEventFilter struct {
	PoolKey    string      // filter by pool key (empty = any)
	PositionID string      // filter by position ID (empty = any)
	Source     RiskSource  // filter by source (empty = any)
	Since      int64       // filter by timestamp >= since (0 = any)
	Limit      int         // maximum results (0 = use default)
}

// ErrRiskEventNotFound is returned when a risk event is not found.
var ErrRiskEventNotFound = &RiskEventNotFoundError{}

type RiskEventNotFoundError struct{}

func (e *RiskEventNotFoundError) Error() string   { return "risk event not found" }
func (e *RiskEventNotFoundError) Is(target error) bool {
	_, ok := target.(*RiskEventNotFoundError)
	return ok
}
