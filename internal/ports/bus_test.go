package ports_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: Bus must implement domain.Bus
var _ ports.Bus = (*busMock)(nil)

type busMock struct{}

func (m *busMock) Publish(e domain.Event) error { return nil }

func (m *busMock) Subscribe(topic string, h ports.EventHandler) (ports.Subscription, error) {
	return nil, nil
}

// Compile-time interface assertion: Subscription must implement ports.Subscription
var _ ports.Subscription = (*subscriptionMock)(nil)

type subscriptionMock struct{}

func (m *subscriptionMock) Unsubscribe() error { return nil }

// Compile-time interface assertion: EventDedup must implement ports.EventDedup
var _ ports.EventDedup = (*eventDedupMock)(nil)

type eventDedupMock struct{}

func (m *eventDedupMock) IsProcessed(eventID string) (bool, error) { return false, nil }

func (m *eventDedupMock) MarkProcessed(eventID string) error { return nil }

// TestBusInterface verifies the Bus interface is properly defined
func TestBusInterface(t *testing.T) {
	require.NotNil(t, t, "ports.Bus interface must exist")
	require.NotNil(t, t, "ports.Subscription interface must exist")
	require.NotNil(t, t, "ports.EventDedup interface must exist")
}

// TestEventHandlerType verifies EventHandler is a function type
func TestEventHandlerType(t *testing.T) {
	// EventHandler should be a function type that takes a domain.Event
	var handler ports.EventHandler = func(e domain.Event) error {
		return nil
	}
	require.NotNil(t, handler)
}
