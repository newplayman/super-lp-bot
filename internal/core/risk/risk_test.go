package risk_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/core/risk"
)

func TestRiskNotImplemented(t *testing.T) {
	t.Skip("Phase 1 task T-312: implement Assess")
	_ = risk.New()
}
