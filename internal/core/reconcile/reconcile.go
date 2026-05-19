package reconcile

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// defaultReconcile is the scaffold stub implementation that panics on use.
// Real implementation will be added in later phases.
//
// In Phase 0, this stub exists only to establish the interface contract
// and allow other modules to compile. Usage in production will panic.
type defaultReconcile struct{}

// New creates a new Reconciler instance.
// In Phase 0, this returns a stub that panics on all operations.
func New() Reconciler {
	return &defaultReconcile{}
}

// Reconcile implements Reconciler.Reconcile with a panic stub.
// This is the bootstrap reconciliation for a specific chain.
// Phase 1 task: T-501
func (r *defaultReconcile) Reconcile(ctx context.Context, chain domain.ChainID, walletAddr domain.Address) (*ports.ReconResult, error) {
	panic("reconcile: defaultReconcile is a scaffold stub; real implementation pending Phase 1: " +
		fmt.Sprintf("chain=%s wallet=%s", chain, walletAddr))
}

// IsReady implements Reconciler.IsReady with a panic stub.
// Returns false until bootstrap completes successfully.
// Phase 1 task: T-501
func (r *defaultReconcile) IsReady() bool {
	panic("reconcile: defaultReconcile is a scaffold stub; real implementation pending Phase 1")
}

// Bootstrap implements Reconciler.Bootstrap with a panic stub.
// Phase 1 task: T-501
func (r *defaultReconcile) Bootstrap(ctx context.Context) error {
	panic("reconcile: defaultReconcile is a scaffold stub; real implementation pending Phase 1")
}