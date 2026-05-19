// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/ports"
)

// RiskRepo implements ports.RiskRepo using SQLite.
// This is a Phase 0 stub implementation.
type RiskRepo struct {
	db interface{}
}

// NewRiskRepo creates a new RiskRepo.
func NewRiskRepo() *RiskRepo {
	return &RiskRepo{}
}

// Compile-time interface assertion
var _ ports.RiskRepo = (*RiskRepo)(nil)

// AppendRiskEvent appends a new risk event to the audit trail.
func (r *RiskRepo) AppendRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	return fmt.Errorf("not implemented: T-131 RiskRepo.AppendRiskEvent")
}

// ListRiskEvents returns risk events matching the provided filters.
func (r *RiskRepo) ListRiskEvents(ctx context.Context, filter ports.RiskEventFilter) ([]ports.RiskEvent, error) {
	return nil, fmt.Errorf("not implemented: T-131 RiskRepo.ListRiskEvents")
}

// GetKillState retrieves the current kill switch state.
func (r *RiskRepo) GetKillState(ctx context.Context) (ports.KillState, error) {
	return ports.KillState{Level: ports.KillLevelOK}, nil
}

// UpsertKillState updates the kill switch state.
func (r *RiskRepo) UpsertKillState(ctx context.Context, state ports.KillState) error {
	return fmt.Errorf("not implemented: T-131 RiskRepo.UpsertKillState")
}