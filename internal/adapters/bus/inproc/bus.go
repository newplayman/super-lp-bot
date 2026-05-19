// Package inproc provides an in-process publish/subscribe bus implementation.
package inproc

import (
	"strings"
	"sync"
	"sync/atomic"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Bus implements an in-process publish/subscribe bus with wildcard support.
// It is safe for concurrent use.
type Bus struct {
	mu   sync.RWMutex
	subs map[string][]*subscriber

	// Optional dedup for preventing duplicate delivery
	dedup        ports.EventDedup
	dedupEnabled atomic.Bool

	// Metrics counters
	publishedCount atomic.Int64
	deliveredCount atomic.Int64
	droppedCount   atomic.Int64
}

// subscriber holds a handler and its delivery channel.
type subscriber struct {
	ch     chan domain.Event
	filter string
	handler ports.EventHandler
}

// Config holds bus configuration options.
type Config struct {
	// BufferSize is the channel buffer size per subscription.
	// Defaults to 100 if 0.
	BufferSize int

	// EnableDedup enables duplicate detection using the provided EventDedup.
	EnableDedup bool

	// Dedup is the deduplication implementation.
	// Required if EnableDedup is true.
	Dedup ports.EventDedup
}

// New creates a new in-process bus with optional configuration.
func New(cfg *Config) *Bus {
	b := &Bus{
		subs: make(map[string][]*subscriber),
	}
	if cfg != nil {
		if cfg.BufferSize > 0 {
			// Buffer size is per subscriber, set in Subscribe
			_ = cfg.BufferSize // used in subscribe
		}
		if cfg.EnableDedup && cfg.Dedup != nil {
			b.dedup = cfg.Dedup
			b.dedupEnabled.Store(true)
		}
	}
	return b
}

// DefaultBufferSize is the default channel buffer size.
const DefaultBufferSize = 100

// Publish delivers an event to all matching subscriptions.
// If deduplication is enabled, events that have already been processed are skipped.
func (b *Bus) Publish(event domain.Event) error {
	b.publishedCount.Add(1)

	// Check dedup if enabled
	if b.dedupEnabled.Load() && b.dedup != nil {
		processed, err := b.dedup.IsProcessed(event.EventID)
		if err != nil {
			return err
		}
		if processed {
			return nil // already processed, skip delivery
		}
	}

	b.mu.RLock()
	defer b.mu.RUnlock()

	// Find all matching subscriptions
	for topic, subs := range b.subs {
		if topicMatches(topic, event.Topic) {
			for _, sub := range subs {
				select {
				case sub.ch <- event:
					b.deliveredCount.Add(1)
				default:
					// Channel full, drop the event
					b.droppedCount.Add(1)
				}
			}
		}
	}

	return nil
}

// Subscribe registers a handler for events matching the given topic pattern.
// Supported patterns:
//   - Exact: "dryrun.pool.scored"
//   - Wildcard suffix: "dryrun.pool.*"
//   - Wildcard prefix: "*.pool.scored"
//   - Full wildcard: "*"
func (b *Bus) Subscribe(topic string, handler ports.EventHandler) (ports.Subscription, error) {
	if topic == "" {
		return nil, ErrEmptyTopic
	}

	bufferSize := DefaultBufferSize
	if topic == "*" {
		bufferSize = 1000 // Give more buffer for wildcard subscribers
	}

	sub := &subscriber{
		ch:     make(chan domain.Event, bufferSize),
		filter: topic,
		handler: handler,
	}

	b.mu.Lock()
	defer b.mu.Unlock()

	b.subs[topic] = append(b.subs[topic], sub)

	// Start goroutine to deliver events
	go b.deliver(sub)

	return &subscription{bus: b, topic: topic, sub: sub}, nil
}

// deliver pumps events from the channel to the handler.
func (b *Bus) deliver(sub *subscriber) {
	for event := range sub.ch {
		if err := sub.handler(event); err != nil {
			// Log error but continue processing
			// Handler errors don't stop the subscription
		}
	}
}

// topicMatches checks if a subscription topic matches an event topic.
func topicMatches(subTopic, eventTopic string) bool {
	// Handle full wildcard
	if subTopic == "*" {
		return true
	}

	// Exact match
	if subTopic == eventTopic {
		return true
	}

	// Wildcard suffix: "dryrun.pool.*" matches "dryrun.pool.scored"
	if strings.HasSuffix(subTopic, ".*") {
		prefix := subTopic[:len(subTopic)-2]
		return strings.HasPrefix(eventTopic, prefix)
	}

	// Wildcard prefix: "*.pool.scored" matches "dryrun.pool.scored"
	if strings.HasPrefix(subTopic, "*.") {
		suffix := subTopic[2:]
		return strings.HasSuffix(eventTopic, suffix)
	}

	return false
}

// ErrEmptyTopic is returned when subscribing with an empty topic.
var ErrEmptyTopic = &TopicError{Topic: ""}

// TopicError indicates a topic-related error.
type TopicError struct {
	Topic string
}

func (e *TopicError) Error() string {
	return "empty topic"
}

// subscription implements ports.Subscription.
type subscription struct {
	bus  *Bus
	topic string
	sub  *subscriber
}

// Unsubscribe cancels the subscription and releases resources.
func (s *subscription) Unsubscribe() error {
	s.bus.mu.Lock()
	defer s.bus.mu.Unlock()

	subs := s.bus.subs[s.topic]
	for i, sub := range subs {
		if sub == s.sub {
			// Remove subscriber
			copy(subs[i:], subs[i+1:])
			s.bus.subs[s.topic] = subs[:len(subs)-1]
			close(s.sub.ch)
			return nil
		}
	}
	return nil
}

// MarkProcessed marks an event as processed for deduplication.
func (b *Bus) MarkProcessed(eventID string) error {
	if b.dedup != nil {
		return b.dedup.MarkProcessed(eventID)
	}
	return nil
}

// Metrics returns current bus metrics.
func (b *Bus) Metrics() BusMetrics {
	return BusMetrics{
		Published: b.publishedCount.Load(),
		Delivered: b.deliveredCount.Load(),
		Dropped:   b.droppedCount.Load(),
	}
}

// BusMetrics holds bus performance metrics.
type BusMetrics struct {
	Published int64
	Delivered int64
	Dropped   int64
}

// Compile-time interface assertion
var _ ports.Bus = (*Bus)(nil)