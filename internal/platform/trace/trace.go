// Package trace provides OpenTelemetry tracing with a noop exporter for Phase 0.
//
// Per spec §7.1: traces → OpenTelemetry → OTLP → Jaeger (Phase 2).
// Phase 0 uses a noop exporter stub that will be replaced with real OTLP later.
package trace

import (
	"context"
	"crypto/rand"
	"encoding/hex"
)

// Context carries trace context across the system.
// In Phase 2, this will embed opentelemetry's propagation Context.
type Context struct {
	TraceID string
}

// Span represents an in-progress trace span.
type Span interface {
	End()
	SetAttribute(key string, value interface{})
}

// Tracer creates spans and propagates trace context.
type Tracer interface {
	StartSpan(ctx Context, name string) (Context, Span)
}

// NoopTracer is a no-operation tracer for Phase 0.
type NoopTracer struct{}

// NewNoopTracer creates a tracer that does nothing (Phase 0 stub).
func NewNoopTracer() *NoopTracer {
	return &NoopTracer{}
}

// StartSpan implements Tracer.
func (t *NoopTracer) StartSpan(ctx Context, name string) (Context, Span) {
	return ctx, &noopSpan{}
}

// noopSpan is a no-operation span for Phase 0.
type noopSpan struct{}

// End implements Span.
func (s *noopSpan) End() {}

// SetAttribute implements Span.
func (s *noopSpan) SetAttribute(key string, value interface{}) {}

// NewTraceID generates a new trace ID.
// Format: 32 hex characters (128 bits), matching W3C TraceContext spec.
// In Phase 2, this will use opentelemetry/sdk/trace.generateTraceID().
func NewTraceID() string {
	return generateUUIDv7()
}

// generateUUIDv7 creates a time-ordered UUID v7.
// This is a stub implementation; Phase 2 will use a proper UUID v7 library.
func generateUUIDv7() string {
	// Generate 16 random bytes for a UUID-like trace ID
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		// Fallback: never actually happens with crypto/rand
		return "00000000000000000000000000000000"
	}
	return hex.EncodeToString(b)
}

// Compile-time check that NoopTracer implements Tracer.
var _ Tracer = (*NoopTracer)(nil)

// Compile-time check that noopSpan implements Span.
var _ Span = (*noopSpan)(nil)

// contextFromStdlib extracts trace context from standard library context.Context.
// Stub for Phase 2 integration with opentelemetry/context.propagation.
func contextFromStdlib(ctx context.Context) Context {
	return Context{}
}

// stdlibContextFromTrace converts our trace Context back to context.Context.
// Stub for Phase 2 integration.
func stdlibContextFromTrace(ctx Context) context.Context {
	return context.Background()
}