//go:build !disable_mev

// Package flashbots implements the Flashbots MEV protection adapter for lp-bot.
//
// This adapter submits transactions through Flashbots Protect API to protect
// against front-running and sandwich attacks on Base/EVM chains.
//
// The adapter is NOT compiled into dryrun/shadow builds (build tag !disable_mev
// ensures it is excluded when MEV protection is disabled).
package flashbots

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// mevSubmitter implements the ports.MEVSubmitter interface for Flashbots MEV protection.
type mevSubmitter struct {
	// TODO: Add Flashbots API client
	// This is a stub that implements the interface but does not actually submit.
	// Phase 3 implementation will add actual Flashbots API integration.
}

// New creates a new Flashbots MEV submitter instance.
//
// Configuration is adapter-specific and may include:
//   - Flashbots Protect API endpoint
//   - Bloxroute auth headers (fallback)
func New(ctx context.Context) (ports.MEVSubmitter, error) {
	return &mevSubmitter{}, nil
}

// Submit submits a signed transaction to Flashbots Protect for MEV-protected execution.
//
// TODO (Phase 3): Implement actual Flashbots API submission.
// Currently this is a stub that returns an empty successful result.
func (m *mevSubmitter) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	// TODO (Phase 3): Implement actual Flashbots submission
	// - Connect to Flashbots Protect API
	// - Submit signed transaction
	// - Handle bundle results and fallbacks
	// - Implement Bloxroute fallback as per spec §6.7

	return ports.MEVSubmissionResult{}, nil
}

// Type returns the type identifier for this MEV submitter.
func (m *mevSubmitter) Type() string {
	return "flashbots"
}