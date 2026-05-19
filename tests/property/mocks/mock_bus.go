package mocks

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// MockBus implements ports.Bus for testing.
type MockBus struct {
	PublishedEvents []domain.Event
	Subscriptions   []*MockSubscription

	PublishHook    func(event domain.Event) error
	SubscribeHook  func(topic string, handler ports.EventHandler) (ports.Subscription, error)
}

func NewMockBus() *MockBus {
	return &MockBus{
		PublishedEvents: make([]domain.Event, 0),
		Subscriptions:   make([]*MockSubscription, 0),
	}
}

func (m *MockBus) Publish(event domain.Event) error {
	if m.PublishHook != nil {
		return m.PublishHook(event)
	}
	m.PublishedEvents = append(m.PublishedEvents, event)
	return nil
}

func (m *MockBus) Subscribe(topic string, handler ports.EventHandler) (ports.Subscription, error) {
	if m.SubscribeHook != nil {
		return m.SubscribeHook(topic, handler)
	}
	sub := &MockSubscription{
		Topic:   topic,
		Handler: handler,
		Active:  true,
	}
	m.Subscriptions = append(m.Subscriptions, sub)
	return sub, nil
}

func (m *MockBus) PublishEvent(event domain.Event) {
	_ = m.Publish(event)
}

func (m *MockBus) ClearEvents() {
	m.PublishedEvents = make([]domain.Event, 0)
}

// MockSubscription implements ports.Subscription for testing.
type MockSubscription struct {
	Topic   string
	Handler ports.EventHandler
	Active  bool
}

func (s *MockSubscription) Unsubscribe() error {
	s.Active = false
	return nil
}

// MockEventDedup implements ports.EventDedup for testing.
type MockEventDedup struct {
	Processed map[string]bool
	IsProcessedHook func(eventID string) (bool, error)
	MarkProcessedHook func(eventID string) error
}

func NewMockEventDedup() *MockEventDedup {
	return &MockEventDedup{
		Processed: make(map[string]bool),
	}
}

func (m *MockEventDedup) IsProcessed(eventID string) (bool, error) {
	if m.IsProcessedHook != nil {
		return m.IsProcessedHook(eventID)
	}
	return m.Processed[eventID], nil
}

func (m *MockEventDedup) MarkProcessed(eventID string) error {
	if m.MarkProcessedHook != nil {
		return m.MarkProcessedHook(eventID)
	}
	m.Processed[eventID] = true
	return nil
}