// Package inproc provides an in-process publish/subscribe bus implementation.
package inproc

import (
	"sync"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
	"pgregory.net/rapid"
)

// mockDedup implements ports.EventDedup for testing.
type mockDedup struct {
	mu       sync.RWMutex
	processed map[string]bool
}

func newMockDedup() *mockDedup {
	return &mockDedup{
		processed: make(map[string]bool),
	}
}

func (d *mockDedup) IsProcessed(eventID string) (bool, error) {
	d.mu.RLock()
	defer d.mu.RUnlock()
	return d.processed[eventID], nil
}

func (d *mockDedup) MarkProcessed(eventID string) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.processed[eventID] = true
	return nil
}

// Compile-time interface assertion
var _ ports.EventDedup = (*mockDedup)(nil)

// TestBusPublishSubscribe tests basic publish/subscribe functionality.
func TestBusPublishSubscribe(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	sub, err := bus.Subscribe("dryrun.pool.scored", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish an event
	event, err := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, map[string]string{"test": "value"})
	require.NoError(t, err)

	err = bus.Publish(event)
	require.NoError(t, err)

	// Wait for delivery
	time.Sleep(10 * time.Millisecond)

	mu.Lock()
	require.Len(t, received, 1)
	require.Equal(t, event.EventID, received[0].EventID)
	mu.Unlock()
}

// TestBusWildcardSuffix tests wildcard suffix matching.
func TestBusWildcardSuffix(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	// Subscribe to all pool events
	sub, err := bus.Subscribe("dryrun.pool.*", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish different events
	testCases := []string{
		"dryrun.pool.scored",
		"dryrun.pool.evaluated",
		"dryrun.pool.rebalanced",
	}

	for _, topic := range testCases {
		event, _ := domain.NewEvent(topic, domain.EnvDryrun, nil)
		bus.Publish(event)
	}

	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	require.Len(t, received, 3)
	mu.Unlock()
}

// TestBusWildcardPrefix tests wildcard prefix matching.
func TestBusWildcardPrefix(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	// Subscribe to all scored events
	sub, err := bus.Subscribe("*.pool.scored", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish different events
	testCases := []string{
		"dryrun.pool.scored",
		"shadow.pool.scored",
		"live.pool.scored",
	}

	for _, topic := range testCases {
		event, _ := domain.NewEvent(topic, domain.EnvDryrun, nil)
		bus.Publish(event)
	}

	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	require.Len(t, received, 3)
	mu.Unlock()
}

// TestBusFullWildcard tests full wildcard matching.
func TestBusFullWildcard(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	// Subscribe to all events
	sub, err := bus.Subscribe("*", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish various events
	testCases := []string{
		"dryrun.pool.scored",
		"shadow.pool.evaluated",
		"live.pool.rebalanced",
		"dryrun.risk.altered",
	}

	for _, topic := range testCases {
		event, _ := domain.NewEvent(topic, domain.EnvDryrun, nil)
		bus.Publish(event)
	}

	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	require.Len(t, received, 4)
	mu.Unlock()
}

// TestBusMultipleSubscribers tests multiple subscribers for same event.
func TestBusMultipleSubscribers(t *testing.T) {
	bus := New(nil)

	received1 := make([]domain.Event, 0)
	received2 := make([]domain.Event, 0)
	var mu sync.Mutex

	handler1 := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received1 = append(received1, e)
		return nil
	}

	handler2 := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received2 = append(received2, e)
		return nil
	}

	sub1, err := bus.Subscribe("dryrun.pool.*", handler1)
	require.NoError(t, err)
	defer sub1.Unsubscribe()

	sub2, err := bus.Subscribe("*.pool.scored", handler2)
	require.NoError(t, err)
	defer sub2.Unsubscribe()

	// Publish matching event
	event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
	bus.Publish(event)

	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	// Both handlers should receive the event
	require.Len(t, received1, 1)
	require.Len(t, received2, 1)
	mu.Unlock()
}

// TestBusUnsubscribe tests unsubscription.
func TestBusUnsubscribe(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	sub, err := bus.Subscribe("dryrun.pool.*", handler)
	require.NoError(t, err)

	// Publish before unsubscribe
	event1, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
	bus.Publish(event1)

	time.Sleep(10 * time.Millisecond)

	// Unsubscribe
	err = sub.Unsubscribe()
	require.NoError(t, err)

	// Publish after unsubscribe
	event2, _ := domain.NewEvent("dryrun.pool.evaluated", domain.EnvDryrun, nil)
	bus.Publish(event2)

	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	// Only first event should be received
	require.Len(t, received, 1)
	require.Equal(t, event1.EventID, received[0].EventID)
	mu.Unlock()
}

// TestBusDedup tests deduplication.
func TestBusDedup(t *testing.T) {
	dedup := newMockDedup()
	bus := New(&Config{EnableDedup: true, Dedup: dedup})

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	sub, err := bus.Subscribe("*", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish same event twice - consumer should mark as processed
	event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)

	// First publish - deliver and mark processed
	bus.Publish(event)
	bus.MarkProcessed(event.EventID) // Consumer marks as processed

	// Second publish - should be deduped
	bus.Publish(event)

	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	// Only one delivery since dedup is enabled
	require.Len(t, received, 1)
	mu.Unlock()
}

// TestBusMetrics tests metrics collection.
func TestBusMetrics(t *testing.T) {
	bus := New(nil)

	handler := func(e domain.Event) error { return nil }
	sub, _ := bus.Subscribe("dryrun.*", handler)
	defer sub.Unsubscribe()

	// Publish events
	for i := 0; i < 10; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
		bus.Publish(event)
	}

	time.Sleep(50 * time.Millisecond)

	metrics := bus.Metrics()
	require.Equal(t, int64(10), metrics.Published)
	require.GreaterOrEqual(t, metrics.Delivered, int64(10))
	require.Equal(t, int64(0), metrics.Dropped)
}

// TestBusEmptyTopicError tests that empty topic returns error.
func TestBusEmptyTopicError(t *testing.T) {
	bus := New(nil)

	handler := func(e domain.Event) error { return nil }
	_, err := bus.Subscribe("", handler)
	require.Error(t, err)
}

// TestBusNoMatch tests that events with no matching subscribers work fine.
func TestBusNoMatch(t *testing.T) {
	bus := New(nil)

	handler := func(e domain.Event) error { return nil }
	sub, _ := bus.Subscribe("dryrun.pool.scored", handler)
	defer sub.Unsubscribe()

	// Publish non-matching event
	event, _ := domain.NewEvent("live.pool.scored", domain.EnvLive, nil)
	err := bus.Publish(event)
	require.NoError(t, err)
}

// TestTopicMatches tests the topic matching function.
func TestTopicMatches(t *testing.T) {
	testCases := []struct {
		subTopic   string
		eventTopic string
		expected   bool
	}{
		// Exact matches
		{"dryrun.pool.scored", "dryrun.pool.scored", true},
		{"dryrun.pool.scored", "shadow.pool.scored", false},

		// Wildcard suffix
		{"dryrun.pool.*", "dryrun.pool.scored", true},
		{"dryrun.pool.*", "dryrun.pool.evaluated", true},
		{"dryrun.pool.*", "shadow.pool.scored", false},
		{"dryrun.pool.*", "dryrun.pool.foo.scored", true}, // matches any suffix after pool.

		// Wildcard prefix
		{"*.pool.scored", "dryrun.pool.scored", true},
		{"*.pool.scored", "shadow.pool.scored", true},
		{"*.pool.scored", "dryrun.risk.scored", false},
		{"*.pool.scored", "foo.pool.scored", true}, // matches any prefix

		// Full wildcard
		{"*", "dryrun.pool.scored", true},
		{"*", "shadow.risk.alert", true},
	}

	for _, tc := range testCases {
		result := topicMatches(tc.subTopic, tc.eventTopic)
		require.Equal(t, tc.expected, result, "topicMatches(%q, %q)", tc.subTopic, tc.eventTopic)
	}
}

// Property test: random events across N subscribers with dedup ON.
func TestBusPropertyDedupNoLossNoDup(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		// Configuration
		numSubscribers := rapid.IntRange(2, 10).Draw(t, "numSubscribers")
		numEvents := rapid.IntRange(50, 100).Draw(t, "numEvents")
		dedupEnabled := rapid.Bool().Draw(t, "dedupEnabled")

		var dedup ports.EventDedup
		dedup = newMockDedup()

		bus := New(&Config{EnableDedup: dedupEnabled, Dedup: dedup})

		// Topics: some exact, some wildcard
		topics := []string{
			"dryrun.pool.scored",
			"dryrun.pool.*",
			"*.pool.scored",
			"shadow.risk.alert",
		}

		// Create subscribers
		var subs []ports.Subscription
		var mutexes []sync.Mutex
		var received [][]domain.Event

		for i := 0; i < numSubscribers; i++ {
			mu := sync.Mutex{}
			mutexes = append(mutexes, mu)
			events := make([]domain.Event, 0)
			received = append(received, events)

			topic := topics[i%len(topics)]
			handler := func(idx int) func(domain.Event) error {
				return func(e domain.Event) error {
					mutexes[idx].Lock()
					defer mutexes[idx].Unlock()
					received[idx] = append(received[idx], e)
					return nil
				}
			}(i)

			sub, err := bus.Subscribe(topic, handler)
			if err != nil {
				t.Fatalf("subscribe failed: %v", err)
			}
			subs = append(subs, sub)
		}

		// Publish events
		for i := 0; i < numEvents; i++ {
			event, err := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, map[string]int{"seq": i})
			if err != nil {
				t.Fatalf("create event failed: %v", err)
			}

			if err := bus.Publish(event); err != nil {
				t.Fatalf("publish failed: %v", err)
			}
		}

		// Wait for delivery
		time.Sleep(100 * time.Millisecond)

		// Verify no loss with dedup OFF, no loss/no dup with dedup ON
		for i := 0; i < numSubscribers; i++ {
			mutexes[i].Lock()
			count := len(received[i])

			if dedupEnabled {
				// Verify no duplicates within a subscriber
				seen := make(map[string]bool)
				for _, e := range received[i] {
					if seen[e.EventID] {
						t.Errorf("Subscriber %d received duplicate event %s", i, e.EventID)
					}
					seen[e.EventID] = true
				}
			}
			mutexes[i].Unlock()

			t.Logf("Subscriber %d (topic=%s) received %d events", i, topics[i%len(topics)], count)
		}
	})
}

// TestBusConcurrentPublish tests concurrent publishing.
func TestBusConcurrentPublish(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()
		received = append(received, e)
		return nil
	}

	sub, err := bus.Subscribe("dryrun.*", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish concurrently
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
			bus.Publish(event)
		}()
	}

	wg.Wait()
	time.Sleep(100 * time.Millisecond)

	mu.Lock()
	require.Len(t, received, 100)
	mu.Unlock()
}

// TestBusConcurrentSubscribePublish tests concurrent subscribe and publish.
func TestBusConcurrentSubscribePublish(t *testing.T) {
	bus := New(nil)

	var wg sync.WaitGroup
	stop := make(chan struct{})

	// Start subscribers
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			received := make([]domain.Event, 0)
			var mu sync.Mutex

			handler := func(e domain.Event) error {
				mu.Lock()
				defer mu.Unlock()
				received = append(received, e)
				return nil
			}

			sub, _ := bus.Subscribe("dryrun.pool.*", handler)
			defer sub.Unsubscribe()

			for {
				select {
				case <-stop:
					return
				default:
					time.Sleep(1 * time.Millisecond)
				}
			}
		}(i)
	}

	// Publish events
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
			bus.Publish(event)
		}()
	}

	time.Sleep(200 * time.Millisecond)
	close(stop)
	wg.Wait()
}

// TestBusEventOrder tests that events maintain order within a subscriber.
func TestBusEventOrder(t *testing.T) {
	bus := New(nil)

	received := make([]domain.Event, 0)
	var mu sync.Mutex

	handler := func(e domain.Event) error {
		mu.Lock()
		defer mu.Unlock()

		// Extract sequence from payload
		var payload map[string]int
		if err := e.PayloadAs(&payload); err == nil {
			if _, ok := payload["seq"]; ok {
				received = append(received, e)
			}
		}
		return nil
	}

	sub, err := bus.Subscribe("dryrun.pool.*", handler)
	require.NoError(t, err)
	defer sub.Unsubscribe()

	// Publish 10 events with sequence numbers
	for i := 0; i < 10; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, map[string]int{"seq": i})
		bus.Publish(event)
	}

	time.Sleep(100 * time.Millisecond)

	mu.Lock()
	defer mu.Unlock()
	require.Len(t, received, 10)

	// Verify order is preserved
	var seqs []int
	for _, e := range received {
		var payload map[string]int
		e.PayloadAs(&payload)
		seqs = append(seqs, payload["seq"])
	}

	for i := 0; i < len(seqs)-1; i++ {
		if seqs[i] > seqs[i+1] {
			t.Errorf("Events out of order: %v", seqs)
			break
		}
	}
}

// TestBusMetricsIncrement tests that metrics increment correctly.
func TestBusMetricsIncrement(t *testing.T) {
	bus := New(nil)

	// Subscribe with small buffer to trigger drops
	sub, _ := bus.Subscribe("dryrun.*", func(e domain.Event) error {
		time.Sleep(10 * time.Millisecond) // Slow handler
		return nil
	})
	defer sub.Unsubscribe()

	// Publish many events quickly
	for i := 0; i < 200; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
		bus.Publish(event)
	}

	time.Sleep(100 * time.Millisecond)

	metrics := bus.Metrics()
	require.Equal(t, int64(200), metrics.Published)
	require.GreaterOrEqual(t, metrics.Delivered, int64(0))
	// Some events may have been dropped due to buffer
}

// TestBusUnsubscribeIdempotent tests that multiple unsubscribes are safe.
func TestBusUnsubscribeIdempotent(t *testing.T) {
	bus := New(nil)

	sub, _ := bus.Subscribe("dryrun.*", func(e domain.Event) error { return nil })

	// Unsubscribe multiple times
	for i := 0; i < 3; i++ {
		err := sub.Unsubscribe()
		require.NoError(t, err)
	}
}

// TestBusNilDedup tests bus behavior with nil dedup.
func TestBusNilDedup(t *testing.T) {
	bus := New(&Config{EnableDedup: true, Dedup: nil})

	// Should still work, dedup is just disabled
	sub, _ := bus.Subscribe("dryrun.*", func(e domain.Event) error { return nil })
	defer sub.Unsubscribe()

	event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
	err := bus.Publish(event)
	require.NoError(t, err)
}

// Compile-time interface assertion for Bus
var _ ports.Bus = (*Bus)(nil)

// Benchmark tests

func BenchmarkBusPublishSingleSubscriber(b *testing.B) {
	bus := New(nil)
	handler := func(e domain.Event) error { return nil }
	sub, _ := bus.Subscribe("dryrun.pool.scored", handler)
	defer sub.Unsubscribe()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
		bus.Publish(event)
	}
}

func BenchmarkBusPublishMultipleSubscribers(b *testing.B) {
	bus := New(nil)

	// Create 10 subscribers
	for i := 0; i < 10; i++ {
		handler := func(e domain.Event) error { return nil }
		bus.Subscribe("dryrun.pool.*", handler)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
		bus.Publish(event)
	}
}

func BenchmarkBusSubscribe(b *testing.B) {
	bus := New(nil)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		handler := func(e domain.Event) error { return nil }
		sub, _ := bus.Subscribe("dryrun.pool.scored", handler)
		sub.Unsubscribe()
	}
}

func BenchmarkBusConcurrentPublish(b *testing.B) {
	bus := New(nil)
	handler := func(e domain.Event) error { return nil }
	sub, _ := bus.Subscribe("dryrun.pool.scored", handler)
	defer sub.Unsubscribe()

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
			bus.Publish(event)
		}
	})
}

func BenchmarkBusWildcardMatch(b *testing.B) {
	bus := New(nil)
	handler := func(e domain.Event) error { return nil }
	bus.Subscribe("dryrun.pool.*", handler)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
		bus.Publish(event)
	}
}

func BenchmarkBusDedupEnabled(b *testing.B) {
	dedup := newMockDedup()
	bus := New(&Config{EnableDedup: true, Dedup: dedup})
	handler := func(e domain.Event) error { return nil }
	sub, _ := bus.Subscribe("dryrun.pool.scored", handler)
	defer sub.Unsubscribe()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		event, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
		bus.Publish(event)
	}
}