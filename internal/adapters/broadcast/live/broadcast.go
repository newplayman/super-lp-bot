//go:build live

// Package live implements the live broadcast adapter for lp-bot.
//
// This adapter is only compiled in live builds (go build -tags live).
// In live builds, transactions are actually broadcast to the network.
//
// In non-live builds (dryrun/shadow), use adapters/broadcast/disabled instead.
package live

import (
	"context"
	"sync/atomic"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// broadcaster implements the ports.Broadcaster interface for live broadcast.
type broadcaster struct {
	// TODO: Add RPC client or other live broadcast implementation
	// This is a stub that tracks call count but does not actually broadcast.
	// Phase 3 implementation will add actual RPC submission.
	callCount int64
}

// New creates a new live broadcaster instance.
//
// Configuration is adapter-specific and may include:
//   - RPC endpoint URL
//   - HTTP headers for authentication
//   - Retry configuration
func New(ctx context.Context) (ports.Broadcaster, error) {
	return &broadcaster{}, nil
}

// Send broadcasts a signed transaction to the network.
//
// TODO (Phase 3): Implement actual broadcast to RPC endpoint.
// Currently this is a stub that records the call for metrics.
func (b *broadcaster) Send(ctx context.Context, tx domain.SignedTx) error {
	atomic.AddInt64(&b.callCount, 1)

	// TODO (Phase 3): Implement actual broadcast
	// - Connect to RPC endpoint
	// - Submit signed transaction
	// - Populate tx.Hash with returned hash
	// - Handle errors and retries

	return nil
}

// CallCount returns the number of times Send has been called.
func (b *broadcaster) CallCount() int64 {
	return atomic.LoadInt64(&b.callCount)
}
