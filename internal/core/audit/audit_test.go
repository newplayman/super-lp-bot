package audit_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/core/audit"
	"github.com/lpbot/lpbot/internal/domain"
)

// TestAuditNotImplemented - Phase 0 scaffold test
// Invariants (spec §9.2): #2 (no duplicate open positions per pool)
func TestAuditNotImplemented(t *testing.T) {
	t.Skip("Phase 1 task T-311: implement Audit")
}

// TestAuditInterface - Phase 0 scaffold test
// Invariants (spec §9.2): #2 (no duplicate open positions per pool)
func TestAuditInterface(t *testing.T) {
	t.Skip("Phase 1 task T-311: implement Audit")

	// Compile-time interface assertion
	var _ audit.Auditor = (*auditMock)(nil)

	_ = context.Background()
	_ = &domain.Pool{}
	_ = &domain.AuditReport{}
}

type auditMock struct{}

func (m *auditMock) Audit(ctx context.Context, pool *domain.Pool) (*domain.AuditReport, error) {
	return nil, nil
}
