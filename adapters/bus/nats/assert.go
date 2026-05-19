package nats

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

var (
	_ ports.Bus                 = (*BusStub)(nil)
	_ ports.EventDedup           = (*EventDedupStub)(nil)
	_ ports.EventDedupContext   = (*EventDedupContextStub)(nil)
)

type (
	BusStub                struct{}
	EventDedupStub        struct{}
	EventDedupContextStub struct{}
)

func (*BusStub) Publish(domain.Event) error                               { return nil }
func (*BusStub) Subscribe(string, ports.EventHandler) (ports.Subscription, error) {
	return &SubscriptionStub{}, nil
}

type SubscriptionStub struct{}

func (*SubscriptionStub) Unsubscribe() error { return nil }

func (*EventDedupStub) IsProcessed(string) (bool, error)    { return false, nil }
func (*EventDedupStub) MarkProcessed(string) error          { return nil }

func (*EventDedupContextStub) IsProcessed(string) (bool, error)            { return false, nil }
func (*EventDedupContextStub) MarkProcessed(string) error                  { return nil }
func (*EventDedupContextStub) IsProcessedContext(context.Context, string) (bool, error) {
	return false, nil
}
func (*EventDedupContextStub) MarkProcessedContext(context.Context, string) error { return nil }