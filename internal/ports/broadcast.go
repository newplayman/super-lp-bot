// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// Broadcast interfaces (this file):
//
//   - Broadcaster: transaction broadcast to the network
//
// See spec §6.7 (table row: Broadcaster).
package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// Broadcaster defines the interface for broadcasting signed transactions to the network.
//
// Implementations handle the actual submission of transactions to the blockchain.
// The behavior depends on the build tag:
//
//   - !live (dryrun/shadow): broadcast/disabled - panics on Send (invariant #3)
//   - live: broadcast/live - submits to the network via RPC or MEV relays
//
// Broadcaster responsibilities (spec §6.7):
//
//   - Send signed transactions to the network
//   - Track call count for metrics (invariant #3: dryrun must be 0)
//   - Emit tx.broadcast event on the bus
//
// The dryrun/shadow build prevents any actual broadcasting by using the disabled
// adapter which panics on any Send call. This ensures invariant #3 is maintained:
// lpbot_dryrun_broadcast_calls_total == 0 for non-live modes.
//
// Usage pattern:
//
//	wallet, _ := walletProvider.Open(ctx, config)
//	broadcaster := broadcastProvider.Open(ctx, config)
//
//	signed, _ := wallet.Sign(ctx, unsignedTx)
//	err := broadcaster.Send(ctx, signed)
//	if err != nil { /* handle failure, potentially retry with RBF */ }
type Broadcaster interface {
	// Send broadcasts a signed transaction to the network.
	//
	// Parameters:
	//   - ctx: context for cancellation and timeout
	//   - tx: the signed transaction to broadcast
	//
	// Returns an error if:
	//   - the transaction fails validation (e.g., malformed)
	//   - the broadcast fails (e.g., RPC error, connection failure)
	//   - the build tag disallows broadcasting (dryrun/shadow panics)
	//
	// On success, the transaction hash (tx.Hash) should be populated if not already set.
	// Callers should also emit a tx.broadcast event on the bus after successful broadcast.
	Send(ctx context.Context, tx domain.SignedTx) error

	// CallCount returns the number of times Send has been called.
	//
	// This is used for metrics and monitoring (invariant #3: dryrun broadcast count must be 0).
	// Implementations should track this atomically for concurrent safety.
	CallCount() int64
}
