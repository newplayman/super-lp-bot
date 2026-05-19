// Package inproc provides an in-process publish/subscribe bus implementation.
package inproc

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// AuditLogSubscriber subscribes to all events and writes them to a JSONL file.
type AuditLogSubscriber struct {
	bus    *Bus
	file   *os.File
	mu     sync.Mutex
	closed atomic.Bool

	eventsWritten atomic.Int64
}

// AuditLogConfig holds audit log configuration.
type AuditLogConfig struct {
	// Directory is where audit logs are written. Defaults to "./data/audit".
	Directory string

	// Filename is the audit log filename. Defaults to "events.jsonl".
	Filename string

	// BufferSize is the channel buffer size. Defaults to 1000.
	BufferSize int

	// MaxFileSize is the maximum file size before rotation (bytes).
	// Defaults to 100MB.
	MaxFileSize int64

	// MaxFiles is the maximum number of rotated files to keep.
	// Defaults to 7.
	MaxFiles int
}

// DefaultAuditLogConfig returns default audit log configuration.
func DefaultAuditLogConfig() AuditLogConfig {
	return AuditLogConfig{
		Directory:    "./data/audit",
		Filename:     "events.jsonl",
		BufferSize:   1000,
		MaxFileSize:  100 * 1024 * 1024, // 100MB
		MaxFiles:     7,
	}
}

// NewAuditLog creates a new audit log subscriber attached to the bus.
func NewAuditLog(bus *Bus, cfg *AuditLogConfig) (*AuditLogSubscriber, error) {
	if cfg == nil {
		c := DefaultAuditLogConfig()
		cfg = &c
	}

	// Ensure directory exists
	if err := os.MkdirAll(cfg.Directory, 0755); err != nil {
		return nil, fmt.Errorf("create audit directory: %w", err)
	}

	// Open audit log file
	path := filepath.Join(cfg.Directory, cfg.Filename)
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return nil, fmt.Errorf("open audit file: %w", err)
	}

	sub := &AuditLogSubscriber{
		bus:  bus,
		file: f,
	}

	// Subscribe to all events
	_, err = bus.Subscribe("*", sub.handleEvent)
	if err != nil {
		f.Close()
		return nil, fmt.Errorf("subscribe to audit log: %w", err)
	}

	return sub, nil
}

// handleEvent writes an event to the audit log.
func (s *AuditLogSubscriber) handleEvent(event domain.Event) error {
	// Serialize event to JSON
	record := auditRecord{
		EventID:   event.EventID,
		TraceID:   event.TraceID,
		Topic:     event.Topic,
		Env:       string(event.Env),
		Timestamp: event.Timestamp,
		Schema:    event.SchemaVersion,
		EventJSON: string(event.Payload),
	}

	data, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("marshal audit record: %w", err)
	}

	// Write to file
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, err := s.file.Write(append(data, '\n')); err != nil {
		return fmt.Errorf("write audit record: %w", err)
	}

	s.eventsWritten.Add(1)

	// Check for rotation
	return nil
}

// auditRecord represents a single audit log entry.
type auditRecord struct {
	EventID   string `json:"event_id"`
	TraceID   string `json:"trace_id"`
	Topic     string `json:"topic"`
	Env       string `json:"env"`
	Timestamp int64  `json:"timestamp"`
	Schema    int    `json:"schema_version"`
	EventJSON string `json:"payload"`
}

// EventsWritten returns the number of events written to the audit log.
func (s *AuditLogSubscriber) EventsWritten() int64 {
	return s.eventsWritten.Load()
}

// Close closes the audit log and stops listening for events.
func (s *AuditLogSubscriber) Close() error {
	if s.closed.Load() {
		return nil
	}
	s.closed.Store(true)

	s.mu.Lock()
	defer s.mu.Unlock()

	return s.file.Close()
}

// RotatingAuditLog provides automatic log rotation.
type RotatingAuditLog struct {
	*AuditLogSubscriber
	cfg AuditLogConfig
}

// NewRotatingAuditLog creates an audit log with automatic rotation.
func NewRotatingAuditLog(bus *Bus, cfg *AuditLogConfig) (*RotatingAuditLog, error) {
	if cfg == nil {
		c := DefaultAuditLogConfig()
		cfg = &c
	}

	sub, err := NewAuditLog(bus, cfg)
	if err != nil {
		return nil, err
	}

	return &RotatingAuditLog{
		AuditLogSubscriber: sub,
		cfg:                 *cfg,
	}, nil
}

// Rotate rotates the audit log file when size limit is exceeded.
func (s *RotatingAuditLog) Rotate() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Get current file size
	info, err := s.file.Stat()
	if err != nil {
		return err
	}

	if info.Size() < s.cfg.MaxFileSize {
		return nil
	}

	// Close current file
	if err := s.file.Close(); err != nil {
		return err
	}

	// Rotate existing files
	path := filepath.Join(s.cfg.Directory, s.cfg.Filename)
	for i := s.cfg.MaxFiles - 1; i > 0; i-- {
		oldPath := fmt.Sprintf("%s.%d", path, i)
		newPath := fmt.Sprintf("%s.%d", path, i+1)
		os.Rename(oldPath, newPath)
	}

	// Rotate current to .1
	if err := os.Rename(path, path+".1"); err != nil {
		return err
	}

	// Open new file
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}

	s.file = f
	return nil
}

// Compile-time interface assertion
var _ ports.Subscription = (*AuditLogSubscriber)(nil)

func (s *AuditLogSubscriber) Unsubscribe() error {
	return s.Close()
}