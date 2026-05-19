// Package reconcile provides bootstrap reconciliation capabilities.
//
// This module compares on-chain state with local database state at startup
// to detect discrepancies before entering live mode.
// See spec §4.6 and module README for details.
package reconcile

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Reconciler defines the interface for bootstrap reconciliation.
// Implementations compare on-chain state with local database state
// and determine whether to allow entry into live mode.
//
// Thread safety: implementations must be safe for concurrent use.
type Reconciler interface {
	// Reconcile performs bootstrap reconciliation for a specific chain.
	//
	// Parameters:
	//   - ctx: context for cancellation
	//   - chain: the blockchain to reconcile
	//   - walletAddr: the wallet address to check positions for
	//
	// Returns a ReconResult with count/value comparison details.
	// Returns an error if the reconciliation cannot be performed.
	//
	// Usage (spec §4.6):
	//   result, err := reconciler.Reconcile(ctx, chain, wallet)
	//   if err != nil || !result.CountMatch || result.ValueDeviationPct > 0.01 {
	//       // reject live entry
	//   }
	Reconcile(ctx context.Context, chain domain.ChainID, walletAddr domain.Address) (*ports.ReconResult, error)

	// IsReady returns whether the reconciler has completed bootstrap successfully.
	// Until bootstrap completes, the system should not enter live mode.
	IsReady() bool

	// Bootstrap performs the full bootstrap reconciliation for all configured chains.
	// This is called once at startup before entering live mode.
	//
	// Parameters:
	//   - ctx: context for cancellation
	//
	// Returns an error if bootstrap fails for any critical chain.
	// After successful bootstrap, IsReady() returns true.
	Bootstrap(ctx context.Context) error
}