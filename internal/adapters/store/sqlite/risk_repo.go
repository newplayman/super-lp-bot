// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
)

// RiskRepo implements ports.RiskRepo using SQLite.
type RiskRepo struct {
	db     *sql.DB
	prefix string
}

// NewRiskRepo creates a new RiskRepo.
func NewRiskRepo(db *sql.DB, prefix string) *RiskRepo {
	return &RiskRepo{db: db, prefix: prefix}
}

// Compile-time interface assertion
var _ ports.RiskRepo = (*RiskRepo)(nil)

// AppendRiskEvent appends a new risk event to the audit trail.
// Schema: id, position_id, pool_key, event_type, action, severity, description, data, resolved, created_at
func (r *RiskRepo) AppendRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	table := r.prefix + "risk_events"
	query := fmt.Sprintf(`
		INSERT INTO %s (id, position_id, pool_key, event_type, action, severity, description, data, resolved, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, table)

	// Use event.Timestamp if provided, otherwise fallback to now
	timestamp := event.Timestamp
	if timestamp == 0 {
		timestamp = time.Now().UnixMilli()
	}

	_, err := r.db.ExecContext(ctx, query,
		event.ID,
		event.PositionID,
		event.PoolKey,
		string(event.Source), // event_type <- Source
		string(event.Action), // action
		string(event.Level), // severity <- Level
		event.Details,       // description <- Details
		"",                  // data placeholder
		0,                   // resolved (default false)
		timestamp,
	)
	return err
}

// ListRiskEvents returns risk events matching the provided filters.
func (r *RiskRepo) ListRiskEvents(ctx context.Context, filter ports.RiskEventFilter) ([]ports.RiskEvent, error) {
	table := r.prefix + "risk_events"
	query := fmt.Sprintf(`SELECT id, position_id, pool_key, event_type, action, severity, description, data, created_at FROM %s WHERE 1=1`, table)
	args := []interface{}{}

	if filter.PoolKey != "" {
		query += " AND pool_key = ?"
		args = append(args, filter.PoolKey)
	}
	if filter.PositionID != "" {
		query += " AND position_id = ?"
		args = append(args, filter.PositionID)
	}
	if filter.Source != "" {
		query += " AND event_type = ?"
		args = append(args, string(filter.Source))
	}
	if filter.Since > 0 {
		query += " AND created_at >= ?"
		args = append(args, filter.Since)
	}

	query += " ORDER BY created_at DESC"
	if filter.Limit > 0 {
		query += " LIMIT ?"
		args = append(args, filter.Limit)
	} else {
		query += " LIMIT 100"
	}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list risk events: %w", err)
	}
	defer rows.Close()

	var events []ports.RiskEvent
	for rows.Next() {
		var e ports.RiskEvent
		var data string
		err := rows.Scan(&e.ID, &e.PositionID, &e.PoolKey, &e.Source, &e.Action, &e.Level, &e.Details, &data, &e.Timestamp)
		if err != nil {
			continue
		}
		events = append(events, e)
	}

	return events, rows.Err()
}

// GetKillState retrieves the current kill switch state.
// Schema: id, switch_type, triggered_at, trigger_reason, auto_resume_at, resumed_at, resume_allowed
func (r *RiskRepo) GetKillState(ctx context.Context) (ports.KillState, error) {
	table := r.prefix + "kill_switch_state"
	query := fmt.Sprintf(`SELECT switch_type, triggered_at, trigger_reason FROM %s ORDER BY triggered_at DESC LIMIT 1`, table)

	var state ports.KillState
	var switchType string
	var triggeredAt int64

	err := r.db.QueryRowContext(ctx, query).Scan(&switchType, &triggeredAt, &state.Reason)
	if err == sql.ErrNoRows {
		return ports.KillState{Level: ports.KillLevelOK}, nil
	}
	if err != nil {
		return ports.KillState{Level: ports.KillLevelOK}, nil
	}

	state.Since = time.UnixMilli(triggeredAt)

	// Determine kill level based on switch type
	switch switchType {
	case "daily_dd":
		state.Level = ports.KillLevelWarn
	case "weekly_dd":
		state.Level = ports.KillLevelFreeze
	case "manual":
		state.Level = ports.KillLevelKill
	case "warn":
		state.Level = ports.KillLevelWarn
	case "freeze":
		state.Level = ports.KillLevelFreeze
	case "kill":
		state.Level = ports.KillLevelKill
	default:
		state.Level = ports.KillLevelOK
	}

	return state, nil
}

// UpsertKillState updates the kill switch state.
// Updates all fields including switch_type and triggered_at when level changes.
func (r *RiskRepo) UpsertKillState(ctx context.Context, state ports.KillState) error {
	table := r.prefix + "kill_switch_state"
	query := fmt.Sprintf(`
		INSERT INTO %s (id, switch_type, triggered_at, trigger_reason, resume_allowed, updated_at)
		VALUES (?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			switch_type = excluded.switch_type,
			triggered_at = excluded.triggered_at,
			trigger_reason = excluded.trigger_reason,
			updated_at = excluded.updated_at
	`, table)

	now := time.Now()
	triggeredAt := state.Since
	if triggeredAt.IsZero() {
		triggeredAt = now
	}

	// Map level to switch_type string
	switchType := string(state.Level)
	if state.Level == "" {
		switchType = "ok"
	}

	_, err := r.db.ExecContext(ctx, query,
		"kill_switch_state",
		switchType,
		triggeredAt.UnixMilli(),
		state.Reason,
		1, // resume_allowed default
		now.UnixMilli(),
	)
	return err
}