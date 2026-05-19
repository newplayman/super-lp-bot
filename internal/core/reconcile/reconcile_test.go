package reconcile_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/core/reconcile"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

func TestReconcileNotImplemented(t *testing.T) {
	// Phase 0: Reconcile stub should exist but panic on operations
	r := reconcile.New()
	if r == nil {
		t.Fatal("reconcile.New() returned nil")
	}
	// Skip actual operation tests - they will panic as expected
	t.Skip("Phase 1 task T-501: implement Reconcile")
}

func TestReconcileInterface(t *testing.T) {
	// Compile-time interface assertion
	var _ reconcile.Reconciler = (*reconcileMock)(nil)
}

type reconcileMock struct{}

func (m *reconcileMock) Reconcile(ctx context.Context, chain domain.ChainID, walletAddr domain.Address) (*ports.ReconResult, error) {
	return nil, nil
}

func (m *reconcileMock) IsReady() bool {
	return false
}

func (m *reconcileMock) Bootstrap(ctx context.Context) error {
	return nil
}