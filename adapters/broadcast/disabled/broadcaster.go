//go:build !live

// Package disabled provides a broadcaster adapter that panics on Send.
// This adapter is used for non-live builds (dryrun, shadow) to enforce
// invariant #3: lpbot_dryrun_broadcast_calls_total must be 0.
//
// When this adapter's Send method is called, it:
//   - Increments the dryrun broadcast counter (for metrics)
//   - Increments the internal atomic counter
//   - Panics to enforce that no actual broadcasting occurs
//
// Use the live adapter (broadcast/live) for actual transaction submission.
package disabled

import (
	"context"
	"sync/atomic"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/metrics"
	"github.com/lpbot/lpbot/internal/ports"
)

// dryrunBroadcastCalls tracks the total number of broadcast attempts
// in non-live builds. This metric is used to verify invariant #3:
// lpbot_dryrun_broadcast_calls_total must be 0 for dryrun/shadow modes.
var dryrunBroadcastCalls = metrics.Counter(
	"lpbot_dryrun_broadcast_calls_total",
	"Total number of broadcast attempts in non-live builds (should always be 0)",
)

// Broadcaster is a broadcaster adapter that panics on any Send call.
// It is used for dryrun and shadow builds to prevent accidental broadcasting.
type Broadcaster struct {
	count atomic.Uint64
}

// Compile-time interface assertion: Broadcaster must implement ports.Broadcaster
var _ ports.Broadcaster = (*Broadcaster)(nil)

// Send panics to prevent any broadcast in non-live builds.
//
// This enforces invariant #3: no transactions should be broadcasted
// in dryrun or shadow mode.
func (b *Broadcaster) Send(ctx context.Context, tx domain.SignedTx) error {
	dryrunBroadcastCalls.Inc()
	b.count.Add(1)
	panic("invariant #3 violation: broadcaster.Send invoked in non-live build")
}

// CallCount returns the number of times Send has been called.
// This is used for metrics and testing verification.
func (b *Broadcaster) CallCount() int64 {
	return int64(b.count.Load())
}