// Package audit provides pool security audit capabilities.
//
// Auditors analyze pools for rug pulls, honeypots, and fee-on-transfer tokens.
// See spec §3.2 and module README for details.
package audit

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// Auditor defines the interface for performing security audits on pools.
// Implementations analyze pool contracts for various risk indicators
// and return an AuditReport with findings and overall verdict.
//
// Thread safety: implementations must be safe for concurrent use.
type Auditor interface {
	// Audit performs a security audit on the given pool.
	//
	// Parameters:
	//   - ctx: context for cancellation
	//   - pool: the pool to audit (must not be nil)
	//
	// Returns an AuditReport with findings or an error if the audit failed.
	// Errors should be considered transient; callers may retry.
	//
	// Example usage:
	//   report, err := auditor.Audit(ctx, pool)
	//   if report.Verdict == domain.AuditFail {
	//       // pool is unsafe, skip it
	//   }
	Audit(ctx context.Context, pool *domain.Pool) (*domain.AuditReport, error)
}