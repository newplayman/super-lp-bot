// Package postgres provides PostgreSQL-backed storage adapters for lp-bot.
package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
)

// RiskRepo implements ports.RiskRepo using PostgreSQL.
type RiskRepo struct {
	db *sql.DB
}

// NewRiskRepo creates a new RiskRepo backed by the given database.
func NewRiskRepo(db *sql.DB) *RiskRepo {
	return &RiskRepo{db: db}
}

// Compile-time interface assertion
var _ ports.RiskRepo = (*RiskRepo)(nil)

// AppendRiskEvent appends a new risk event to the audit trail.
func (r *RiskRepo) AppendRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO risk_events (
			id, position_id, pool_key, source, action, level, details, timestamp
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (id) DO NOTHING
	`,
		event.ID,
		event.PositionID,
		event.PoolKey,
		string(event.Source),
		string(event.Action),
		string(event.Level),
		event.Details,
		event.Timestamp,
	)
	if err != nil {
		return fmt.Errorf("failed to append risk event: %w", err)
	}
	return nil
}

// ListRiskEvents returns risk events matching the provided filters.
func (r *RiskRepo) ListRiskEvents(ctx context.Context, filter ports.RiskEventFilter) ([]ports.RiskEvent, error) {
	query := `
		SELECT id, position_id, pool_key, source, action, level, details, timestamp
		FROM risk_events
		WHERE 1=1
	`
	args := []interface{}{}
	argIdx := 1

	if filter.PoolKey != "" {
		query += fmt.Sprintf(" AND pool_key = $%d", argIdx)
		args = append(args, filter.PoolKey)
		argIdx++
	}

	if filter.PositionID != "" {
		query += fmt.Sprintf(" AND position_id = $%d", argIdx)
		args = append(args, filter.PositionID)
		argIdx++
	}

	if filter.Source != "" {
		query += fmt.Sprintf(" AND source = $%d", argIdx)
		args = append(args, string(filter.Source))
		argIdx++
	}

	if filter.Since > 0 {
		query += fmt.Sprintf(" AND timestamp >= $%d", argIdx)
		args = append(args, filter.Since)
		argIdx++
	}

	query += " ORDER BY timestamp DESC"

	limit := filter.Limit
	if limit <= 0 {
		limit = 100
	}
	query += fmt.Sprintf(" LIMIT $%d", argIdx)
	args = append(args, limit)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list risk events: %w", err)
	}
	defer rows.Close()

	var events []ports.RiskEvent
	for rows.Next() {
		var event ports.RiskEvent
		err := rows.Scan(
			&event.ID,
			&event.PositionID,
			&event.PoolKey,
			&event.Source,
			&event.Action,
			&event.Level,
			&event.Details,
			&event.Timestamp,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan risk event: %w", err)
		}
		events = append(events, event)
	}

	return events, rows.Err()
}

// GetKillState retrieves the current kill switch state.
func (r *RiskRepo) GetKillState(ctx context.Context) (ports.KillState, error) {
	var state ports.KillState
	var sourcesStr string

	err := r.db.QueryRowContext(ctx, `
		SELECT level, sources, since, reason, unlocker
		FROM kill_switch_state
		ORDER BY id DESC
		LIMIT 1
	`).Scan(&state.Level, &sourcesStr, &state.Since, &state.Reason, &state.Unlocker)

	if err == sql.ErrNoRows {
		return ports.KillState{Level: ports.KillLevelOK}, nil
	}
	if err != nil {
		return ports.KillState{}, fmt.Errorf("failed to get kill state: %w", err)
	}

	// Parse sources from comma-separated string
	if sourcesStr != "" {
		state.Sources = parseSources(sourcesStr)
	}

	return state, nil
}

// UpsertKillState updates the kill switch state.
func (r *RiskRepo) UpsertKillState(ctx context.Context, state ports.KillState) error {
	sourcesStr := joinSources(state.Sources)

	_, err := r.db.ExecContext(ctx, `
		INSERT INTO kill_switch_state (level, sources, since, reason, unlocker)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (id) DO UPDATE SET
			level = excluded.level,
			sources = excluded.sources,
			since = excluded.since,
			reason = excluded.reason,
			unlocker = excluded.unlocker
	`,
		string(state.Level),
		sourcesStr,
		state.Since.Unix(),
		state.Reason,
		state.Unlocker,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert kill state: %w", err)
	}
	return nil
}

// parseSources parses a comma-separated string into RiskSource slice.
func parseSources(s string) []ports.RiskSource {
	if s == "" {
		return nil
	}
	sources := make([]ports.RiskSource, 0)
	for _, p := range splitAndTrim(s, ",") {
		sources = append(sources, ports.RiskSource(p))
	}
	return sources
}

// joinSources joins a RiskSource slice into a comma-separated string.
func joinSources(sources []ports.RiskSource) string {
	if len(sources) == 0 {
		return ""
	}
	result := ""
	for i, s := range sources {
		if i > 0 {
			result += ","
		}
		result += string(s)
	}
	return result
}

// splitAndTrim splits a string by delimiter and trims whitespace.
func splitAndTrim(s, sep string) []string {
	var result []string
	for _, part := range splitStr(s, sep) {
		trimmed := trimSpace(part)
		if trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func splitStr(s, sep string) []string {
	if s == "" {
		return nil
	}
	var result []string
	start := 0
	for {
		idx := stringIndex(s, sep, start)
		if idx < 0 {
			result = append(result, s[start:])
			break
		}
		result = append(result, s[start:idx])
		start = idx + len(sep)
	}
	return result
}

func stringIndex(s, substr string, start int) int {
	if start >= len(s) {
		return -1
	}
	for i := start; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return i
		}
	}
	return -1
}

func trimSpace(s string) string {
	start := 0
	end := len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t' || s[start] == '\n' || s[start] == '\r') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\n' || s[end-1] == '\r') {
		end--
	}
	return s[start:end]
}

// Helper function for time conversion
func timeFromUnix(unix int64) time.Time {
	return time.Unix(unix, 0)
}