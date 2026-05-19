package domain

import (
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
)

// Env represents the run mode.
type Env string

const (
	EnvDryrun Env = "dryrun"
	EnvShadow Env = "shadow"
	EnvLive   Env = "live"
)

func (e Env) String() string { return string(e) }

// Event is the standard bus event envelope (spec §3.2).
type Event struct {
	EventID       string     // UUID v7 (时间排序) - 幂等键
	TraceID       string     // 贯穿决策链路
	Topic         string     // <env>.<domain>.<event>，如 "dryrun.pool.scored"
	Env           Env
	SchemaVersion int        // always 1 for v1
	Timestamp     int64      // unix nano — wall clock，仅调试
	BlockRef      *BlockRef  // nil if no block
	Payload       []byte     // JSON payload
}

// NewEvent creates a new Event with auto-generated EventID and TraceID.
func NewEvent(topic string, env Env, payload any) (Event, error) {
	id, err := uuid.NewV7()
	if err != nil {
		return Event{}, fmt.Errorf("generate event id: %w", err)
	}

	var traceID = id.String() // default trace to event id if not set
	trace, err := uuid.NewV7()
	if err != nil {
		return Event{}, fmt.Errorf("generate trace id: %w", err)
	}
	traceID = trace.String()

	var payloadBytes []byte
	if payload != nil {
		payloadBytes, err = json.Marshal(payload)
		if err != nil {
			return Event{}, fmt.Errorf("marshal payload: %w", err)
		}
	}

	return Event{
		EventID:       id.String(),
		TraceID:       traceID,
		Topic:         topic,
		Env:           env,
		SchemaVersion: 1,
		Timestamp:     nowNano(),
		BlockRef:      nil,
		Payload:       payloadBytes,
	}, nil
}

// PayloadAs unmarshals the Payload field into v.
func (e *Event) PayloadAs(v any) error {
	if e.Payload == nil {
		return nil
	}
	return json.Unmarshal(e.Payload, v)
}

// String returns a short representation of the event.
func (e *Event) String() string {
	shortID := e.EventID
	if len(shortID) > 8 {
		shortID = shortID[:8]
	}
	return fmt.Sprintf("%s:%s", e.Topic, shortID)
}

// nowNano returns the current wall clock time in Unix nanoseconds.
var nowNano = func() int64 {
	return int64(0) // Will be overridden in tests via injection if needed
}

func init() {
	nowNano = func() int64 {
		return 0 // placeholder; actual time set via mock in tests
	}
}