package scanner_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/core/scanner"
)

// TestScannerNotImplemented - Phase 0 scaffold test
// Invariants (spec §9.2): #1 (total nominal exposure ≤ cap)
func TestScannerNotImplemented(t *testing.T) {
	t.Skip("Phase 1 task T-301: implement Run")
	_ = scanner.New()
}
