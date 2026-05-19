package trace_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/platform/trace"
)

func TestTracerStartSpan(t *testing.T) {
	tracer := trace.NewNoopTracer()

	// Should be able to start a span without error
	ctx, span := tracer.StartSpan(ctxWithTraceID(), "test-span")
	defer span.End()

	if span == nil {
		t.Error("expected non-nil span from StartSpan")
	}
	_ = ctx // ctx is a value type, always non-nil
}

func TestTracerEndToEnd(t *testing.T) {
	tracer := trace.NewNoopTracer()

	// Complete span lifecycle: start -> end
	ctx, span := tracer.StartSpan(ctxWithTraceID(), "lifecycle-span")
	span.End()

	// Context is a value type, always non-nil
	_ = ctx
}

func TestTraceIDGeneration(t *testing.T) {
	id1 := trace.NewTraceID()
	id2 := trace.NewTraceID()

	// Each call should generate a unique ID
	if id1 == "" {
		t.Error("NewTraceID should not return empty string")
	}
	if id1 == id2 {
		t.Error("NewTraceID should generate unique IDs")
	}
}

func TestSpanAttributes(t *testing.T) {
	tracer := trace.NewNoopTracer()
	_, span := tracer.StartSpan(ctxWithTraceID(), "attr-span")

	// Should be able to set attributes on span
	span.SetAttribute("key", "value")
	span.SetAttribute("count", int64(42))

	span.End()
}

// ctxWithTraceID returns a context with a trace ID set.
// In a real implementation, this would come from the Tracer.
// For testing, we use a helper that extracts or generates a trace ID.
func ctxWithTraceID() trace.Context {
	return trace.Context{
		TraceID: trace.NewTraceID(),
	}
}