package audit

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
)

// defaultAudit is the scaffold stub implementation that panics on use.
// Real implementation will be added in later phases.
//
// In Phase 0, this stub exists only to establish the interface contract
// and allow other modules to compile. Usage in production will panic.
type defaultAudit struct{}

// NewDefaultAudit creates a new scaffold audit implementation.
// This implementation panics on any method call to prevent accidental use.
//
// Real audit logic will be implemented in subsequent phases.
// Until then, any attempt to use this auditor will panic with a helpful message.
func NewDefaultAudit() Auditor {
	return &defaultAudit{}
}

// Audit implements Auditor.Audit with a panic stub.
// In production, this should never be called - return an error instead.
func (a *defaultAudit) Audit(_ context.Context, pool *domain.Pool) (*domain.AuditReport, error) {
	panic("audit: defaultAudit is a scaffold stub; real implementation pending Phase 1: " +
		fmt.Sprintf("pool=%s", pool.Key()))
}