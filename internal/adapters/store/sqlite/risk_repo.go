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
func NewRiskRepo(db *sql.DB) *RiskRepo {
	return &RiskRepo{db: db, prefix: "shadow_"}
}

// Compile-time interface assertion
var _ ports.RiskRepo = (*RiskRepo)(nil)

// AppendRiskEvent appends a new risk event to the audit trail.
func (r *RiskRepo) AppendRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	table := r.prefix + "risk_events"
	query := fmt.Sprintf(`
		INSERT INTO %s (id, position_id, pool_key, source, action, level, details, timestamp)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`, table)

	now := time.Now().UnixMilli()

	_, err := r.db.ExecContext(ctx, query,
		event.ID, event.PositionID, event.PoolKey,
		string(event.Source), string(event.Action), string(event.Level),
		event.Details, now,
	)
	return err
}

// ListRiskEvents returns risk events matching the provided filters.
func (r *RiskRepo) ListRiskEvents(ctx context.Context, filter ports.RiskEventFilter) ([]ports.RiskEvent, error) {
	table := r.prefix + "risk_events"
	query := fmt.Sprintf(`SELECT id, position_id, pool_key, source, action, level, details, timestamp FROM %s WHERE 1=1`, table)
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
		query += " AND source = ?"
		args = append(args, string(filter.Source))
	}
	if filter.Since > 0 {
		query += " AND timestamp >= ?"
		args = append(args, filter.Since)
	}

	query += " ORDER BY timestamp DESC"
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
		err := rows.Scan(&e.ID, &e.PositionID, &e.PoolKey, &e.Source, &e.Action, &e.Level, &e.Details, &e.Timestamp)
		if err != nil {
			continue
		}
		events = append(events, e)
	}

	return events, rows.Err()
}

// GetKillState retrieves the current kill switch state.
func (r *RiskRepo) GetKillState(ctx context.Context) (ports.KillState, error) {
	table := r.prefix + "kill_switch_state"
	query := fmt.Sprintf(`SELECT level, sources, since, reason, unlocker FROM %s ORDER BY since DESC LIMIT 1`, table)

	var state ports.KillState
	var sources string

	err := r.db.QueryRowContext(ctx, query).Scan(
		&state.Level, &sources, &state.Since, &state.Reason, &state.Unlocker,
	)
	if err == sql.ErrNoRows {
		return ports.KillState{Level: ports.KillLevelOK}, nil
	}
	if err != nil {
		return ports.KillState{Level: ports.KillLevelOK}, nil
	}

	return state, nil
}

// UpsertKillState updates the kill switch state.
func (r *RiskRepo) UpsertKillState(ctx context.Context, state ports.KillState) error {
	table := r.prefix + "kill_switch_state"
	query := fmt.Sprintf(`
		INSERT INTO %s (id, level, sources, since, reason, unlocker, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			level = excluded.level,
			sources = excluded.sources,
			since = excluded.since,
			reason = excluded.reason,
			unlocker = excluded.unlocker,
			updated_at = excluded.updated_at
	`, table)

	now := time.Now()
	id := "kill_switch_state" // single row

	_, err := r.db.ExecContext(ctx, query,
		id, string(state.Level), "", now,
		state.Reason, state.Unlocker, now,
	)
	return err
}