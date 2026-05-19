// Package nats provides NATS adapter stubs for bus ports.
// This file documents which ports the nats adapter implements.
// Actual implementation deferred to Phase 4.

package nats

import (
	"github.com/lpbot/lpbot/internal/ports"
)

var (
	_ ports.Bus            = (*BusStub)(nil)
	_ ports.EventDedup      = (*EventDedupStub)(nil)
	_ ports.EventDedupContext = (*EventDedupContextStub)(nil)
)

type (
	BusStub             struct{}
	EventDedupStub     struct{}
	EventDedupContextStub struct{}
)