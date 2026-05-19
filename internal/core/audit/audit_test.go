package audit_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/core/audit"
	"github.com/lpbot/lpbot/internal/domain"
)

func TestAuditInterface(t *testing.T) {
	t.Skip("T-071 scaffold: real audit implementation pending Phase 1")

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