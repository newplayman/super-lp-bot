// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// MEV interfaces (this file):
//
//   - MEVSubmitter: MEV-protected transaction submission
//
// See spec §6.7 (MEV protection table).
package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// MEVSubmitOpts holds options for MEV submission.
type MEVSubmitOpts struct {
	// MaxBundleGasLimit is the maximum gas limit for the bundle (EVM/Flashbots).
	// If zero, uses the default limit of the MEV relayer.
	MaxBundleGasLimit uint64

	// JitoTipLamports is the tip in lamports for Jito blockengine (Solana).
	// Only applicable for Solana/Jito submissions.
	JitoTipLamports uint64

	// FastMode indicates whether to use fast mode (Jito).
	// Only applicable for Solana/Jito submissions.
	FastMode bool
}

// MEVSubmissionResult holds the result of an MEV submission attempt.
type MEVSubmissionResult struct {
	// BundleHash is the bundle hash returned by the MEV relayer (Flashbots).
	// Empty if submission was not via Flashbots or if bundle was rejected.
	BundleHash string

	// Signature is the confirmation signature from the blockengine (Jito).
	// Empty if submission was not via Jito or if submission failed.
	Signature string

	// SimulateOnly indicates if the submission was simulation only
	// (not actually submitted to the network).
	SimulateOnly bool
}

// MEVSubmitter defines the interface for MEV-protected transaction submission.
//
// Implementations submit transactions through MEV relays (e.g., Flashbots Protect,
// Jito) to protect against front-running and sandwich attacks. The behavior
// depends on the chain:
//
//   - Base / EVM: mev/flashbots-protect adapter
//   - Solana: mev/jito adapter
//
// MEV protection strategy (spec §6.7):
//
//	┌─────────┐     ┌──────────────┐     ┌──────────────┐
//	│  Base   │────▶│ Flashbots    │────▶│ Bloxroute    │ (fallback)
//	└─────────┘     └──────────────┘     └──────────────┘
//	                                           │
//	                                           ▼
//	                                    ┌──────────────┐
//	                                    │ Public mempool │ (both fail → tx not sent)
//	                                    └──────────────┘
//
//	┌───────────┐     ┌──────────────┐
//	│ Solana    │────▶│ Jito         │────▶ (no fallback, tx not sent)
//	└───────────┘     └──────────────┘
//
// Compilation-time safety (dryrun/shadow builds):
//
// As specified in spec §6.7, MEV submitter adapters are NOT linked into
// dryrun/shadow builds. This prevents accidental real submissions and ensures
// the execution pipeline cannot be used in non-live modes.
//
// Usage pattern:
//
//	submitter := mevProvider.Open(ctx, config)
//
//	signed, _ := wallet.Sign(ctx, unsignedTx)
//	result, err := submitter.Submit(ctx, signed, MEVSubmitOpts{
//	    MaxBundleGasLimit: 5000000,
//	})
//	if err != nil { /* both failed → tx not sent, emit tx.submission_failed */ }
type MEVSubmitter interface {
	// Submit submits a signed transaction to the MEV relay for protected execution.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - tx: the signed transaction to submit
	//   - opts: MEV-specific submission options
	//
	// Returns a MEVSubmissionResult with the result of the submission, or an error if:
	//   - the submission fails (network error, relay error)
	//   - validation fails
	//
	// Callers should emit tx.submission_failed event if both MEV submission
	// and public mempool fallback fail (when fallback is available).
	//
	// Note: The returned result may have empty fields if the submission was rejected.
	// Callers should check the result and error to determine next steps.
	Submit(ctx context.Context, tx domain.SignedTx, opts MEVSubmitOpts) (MEVSubmissionResult, error)

	// Type returns the type identifier for this MEV submitter.
	//
	// Expected values:
	//   - "flashbots": Flashbots Protect API (Base/EVM)
	//   - "jito": Jito blockengine (Solana)
	//   - "disabled": no-op submitter (dryrun/shadow)
	//
	// This is used for logging, metrics, and error messages.
	Type() string
}
