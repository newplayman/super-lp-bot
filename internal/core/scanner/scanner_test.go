package scanner_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/core/scanner"
)

func TestScannerNotImplemented(t *testing.T) {
	t.Skip("Phase 1 task T-301: implement Run")
	_ = scanner.New()
}