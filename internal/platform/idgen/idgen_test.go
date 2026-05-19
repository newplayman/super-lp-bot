package idgen

import (
	"strings"
	"testing"
	"time"
)

func TestEventID_IsV7(t *testing.T) {
	id := NewEventID()
	// UUID v7 format: xxxxxxxx-xxxx-7xxx-yxxx-xxxxxxxxxxxx
	parts := strings.Split(id, "-")
	if len(parts) != 5 {
		t.Fatalf("expected 5 parts, got %d", len(parts))
	}
	if len(parts[0]) != 8 || len(parts[1]) != 4 || len(parts[2]) != 4 || len(parts[3]) != 4 || len(parts[4]) != 12 {
		t.Fatalf("invalid UUID format: %s", id)
	}
	// Version 7: first char of third group must be '7'
	if parts[2][0] != '7' {
		t.Fatalf("expected version 7, got %c in %s", parts[2][0], parts[2])
	}
}

func TestEventID_SequentialOrder(t *testing.T) {
	// Property test: 10000 sequential EventIDs are strictly time-ordered (v7 lexicographic)
	// UUID v7 is lexicographically sortable by timestamp
	const count = 10000
	ids := make([]string, count)
	for i := 0; i < count; i++ {
		ids[i] = NewEventID()
		time.Sleep(time.Microsecond) // ensure different timestamps
	}

	for i := 1; i < count; i++ {
		if ids[i] <= ids[i-1] {
			t.Errorf("EventIDs not strictly increasing at index %d: prev=%s, curr=%s", i, ids[i-1], ids[i])
		}
	}
}

func TestTraceID_Format(t *testing.T) {
	traceID := NewTraceID("scan")
	if !strings.HasPrefix(traceID, "scan-") {
		t.Errorf("expected prefix 'scan-', got %s", traceID)
	}
	// Should have prefix + "-" + 8 hex chars
	parts := strings.Split(traceID, "-")
	if len(parts) != 2 {
		t.Fatalf("expected 2 parts, got %d", len(parts))
	}
	if len(parts[1]) != 8 {
		t.Errorf("expected 8 hex chars, got %d", len(parts[1]))
	}
}

func TestTraceID_UniquePrefix(t *testing.T) {
	scanID := NewTraceID("scan")
	execID := NewTraceID("exec")
	if strings.HasPrefix(scanID, "exec") {
		t.Errorf("scanID should not have exec prefix: %s", scanID)
	}
	if strings.HasPrefix(execID, "scan") {
		t.Errorf("execID should not have scan prefix: %s", execID)
	}
}