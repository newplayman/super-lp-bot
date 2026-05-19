package domain_test

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/lpbot/lpbot/internal/domain"
)

func TestAuditReport_OverallVerdict(t *testing.T) {
	report := domain.AuditReport{
		Findings: []domain.AuditFinding{
			{Category: domain.AuditHoneypot, Verdict: domain.AuditPass},
			{Category: domain.AuditLPNotLocked, Verdict: domain.AuditWarn},
		},
	}
	require.Equal(t, domain.AuditWarn, report.OverallVerdict())

	report.Findings = append(report.Findings,
		domain.AuditFinding{Category: domain.AuditHoneypot, Verdict: domain.AuditFail})
	require.Equal(t, domain.AuditFail, report.OverallVerdict())
}

func TestAuditReport_Score(t *testing.T) {
	report := domain.AuditReport{
		Findings: []domain.AuditFinding{
			{Score: 30},
			{Score: 70},
			{Score: 10},
		},
	}
	require.Equal(t, 70.0, report.MaxScore())
}
