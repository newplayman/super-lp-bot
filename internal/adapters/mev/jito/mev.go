//go:build !disable_mev

// Package jito implements the Jito MEV protection adapter for lp-bot.
//
// This adapter submits transactions through Jito blockengine to protect
// against front-running and sandwich attacks on Solana.
//
// The adapter is NOT compiled into dryrun/shadow builds (build tag !disable_mev
// ensures it is excluded when MEV protection is disabled).
package jito

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// mevSubmitter implements the ports.MEVSubmitter interface for Jito MEV protection.
type mevSubmitter struct {
	// TODO: Add Jito blockengine client
	// This is a stub that implements the interface but does not actually submit.
	// Phase 3 implementation will add actual Jito blockengine integration.
}

// New creates a new Jito MEV submitter instance.
//
// Configuration is adapter-specific and may include:
//   - Jito blockengine endpoints
//   - Tip configuration (JitoTipLamports)
//   - Fast mode settings
func New(ctx context.Context) (ports.MEVSubmitter, error) {
	return &mevSubmitter{}, nil
}

// Submit submits a signed transaction to Jito blockengine for MEV-protected execution.
//
// TODO (Phase 3): Implement actual Jito blockengine submission.
// Currently this is a stub that returns an empty successful result.
func (m *mevSubmitter) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	// TODO (Phase 3): Implement actual Jito submission
	// - Connect to Jito blockengine
	// - Submit signed transaction with tip
	// - Handle fast mode if requested
	// - Return signature from blockengine

	return ports.MEVSubmissionResult{}, nil
}

// Type returns the type identifier for this MEV submitter.
func (m *mevSubmitter) Type() string {
	return "jito"
}