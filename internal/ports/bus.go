// Package ports defines the hexagonal architecture port interfaces.
//
// Ports are the contracts between the core business logic and external
// adapters. Core packages depend only on these interfaces, never on
// concrete adapter implementations.
//
// Bus ports (this file):
//
//   - Bus: publish/subscribe messaging abstraction
//   - Subscription: handle for active subscriptions
//   - EventDedup: event idempotency via processed_events table
//
// See spec §3 for data flow and bus design.
package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// EventHandler is a callback function invoked for each event matching
// a subscription's topic filter. Handlers should be fast and non-blocking;
// long-running work should be dispatched to a goroutine or worker pool.
//
// Errors returned by the handler are logged but do not stop delivery
// of subsequent events to the same subscription.
type EventHandler func(event domain.Event) error

// Bus is the messaging abstraction for publish/subscribe communication
// between core modules. Events flow from producers to consumers via topics.
//
// Bus implementations are responsible for:
//
//   - Topic-based routing: dispatch events to matching subscriptions
//   - Fan-out: each subscription receives its own event copy
//   - At-most-once delivery to inproc adapter; at-least-once via NATS
//
// The Bus itself does not perform deduplication; use EventDedup for that.
//
// See spec §3.4 for adapter implementations.
type Bus interface {
	// Publish sends an event to all subscribers matching the event's Topic.
	// It returns immediately after enqueueing; delivery is asynchronous.
	//
	// Publish is safe to call concurrently.
	//
	// Returns an error only if enqueueing fails (e.g., channel closed).
	// Callers should not retry Publish on error; instead, log and alert.
	Publish(event domain.Event) error

	// Subscribe registers a handler for events matching the given topic.
	// The topic supports the following patterns:
	//
	//   - Exact match: "dryrun.pool.scored"
	//   - Wildcard suffix: "dryrun.pool.*" matches all pool events
	//   - Wildcard prefix: "*.pool.scored" matches all envs
	//   - Full wildcard: "*" matches all events
	//
	// The returned Subscription remains active until Unsubscribe is called.
	// If the topic pattern is invalid, Subscribe returns an error.
	Subscribe(topic string, handler EventHandler) (Subscription, error)
}

// Subscription represents an active subscription to bus events.
// Call Unsubscribe to stop receiving events and release resources.
//
// Subscriptions are not safe for concurrent use; serialize Unsubscribe calls.
type Subscription interface {
	// Unsubscribe cancels the subscription and releases resources.
	// After Unsubscribe returns, the handler will not be invoked again.
	//
	// Unsubscribe is idempotent: calling multiple times returns nil.
	Unsubscribe() error
}

// EventDedup provides idempotency guarantees for event processing.
// It tracks processed event IDs in the processed_events DB table,
// preventing duplicate handling when events are delivered more than once
// (e.g., after a consumer crash or network re-delivery).
//
// EventDedup is used by consumers, not by the Bus itself.
//
// Usage pattern:
//
//	isNew, err := dedup.IsProcessed(eventID)
//	if err != nil { return err }
//	if isNew { return nil } // already processed, skip
//
//	// ... handle event ...
//
//	if err := dedup.MarkProcessed(eventID); err != nil { return err }
//
// See spec §3.2 (processed_events table) and invariant #11.
type EventDedup interface {
	// IsProcessed returns true if the event has already been processed.
	// It checks the processed_events table by event_id.
	//
	// Implementations should use a read transaction (no locks).
	// Returns (false, nil) if not found or (true, nil) if found.
	IsProcessed(eventID string) (bool, error)

	// MarkProcessed records that an event has been successfully processed.
	// It inserts into processed_events with event_id as the idempotency key.
	//
	// Implementations should use INSERT OR IGNORE / ON CONFLICT DO NOTHING
	// to handle concurrent calls gracefully.
	//
	// The processed_events table has a TTL of 7 days (spec §4.7);
	// cleanup is handled by the archive job, not by MarkProcessed.
	MarkProcessed(eventID string) error
}

// EventDedupContext adds context support to EventDedup for cancellation.
type EventDedupContext interface {
	EventDedup

	// IsProcessedContext is like IsProcessed but accepts a context.
	// The context can be used for deadlines or cancellation.
	IsProcessedContext(ctx context.Context, eventID string) (bool, error)

	// MarkProcessedContext is like MarkProcessed but accepts a context.
	MarkProcessedContext(ctx context.Context, eventID string) error
}
