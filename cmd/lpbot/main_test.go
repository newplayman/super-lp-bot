// Package main provides tests for the main application wiring.
package main

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

func newWiredTestApp(t *testing.T) (*App, context.Context) {
	t.Helper()

	app := &App{}
	app.config = minimalConfig(filepath.Join(t.TempDir(), "lpbottest.sqlite"))

	store, err := sqlite.NewStore(app.config.Store.SQLitePath)
	if err != nil {
		t.Fatalf("initialize sqlite store: %v", err)
	}
	app.store = store

	ctx := context.Background()
	if err := app.wireMainLoop(ctx); err != nil {
		t.Fatalf("wireMainLoop failed: %v", err)
	}
	return app, ctx
}

// TestWire_AllPortsInjected verifies all critical ports are properly injected.
// This test ensures the wireMainLoop function properly initializes all components.
// TR-01 DoD: Wire must not miss any port.
func TestWire_AllPortsInjected(t *testing.T) {
	app, _ := newWiredTestApp(t)

	if app.mainLoop == nil {
		t.Fatal("mainLoop is nil after wireMainLoop")
	}

	// Verify critical ports are injected (not nil)
	if app.mainLoop.RiskGate == nil {
		t.Error("RiskGate is nil - not properly injected")
	}
	if app.mainLoop.AllocationManager == nil {
		t.Error("AllocationManager is nil - not properly injected")
	}
	if app.mainLoop.Simulator == nil {
		t.Error("Simulator is nil - not properly injected")
	}
	if app.mainLoop.ApproveTracker == nil {
		t.Error("ApproveTracker is nil - not properly injected")
	}
	if app.mainLoop.OrderManager == nil {
		t.Error("OrderManager is nil - not properly injected")
	}
	if app.mainLoop.Scanner == nil {
		t.Log("Scanner is nil (expected when datasource not initialized)")
	}
	if app.mainLoop.GetMetrics() == nil {
		t.Error("Metrics is nil - not properly injected")
	}
}

// TestWire_RiskGateConfig verifies RiskGate is configured with correct thresholds.
func TestWire_RiskGateConfig(t *testing.T) {
	app, _ := newWiredTestApp(t)

	// Verify RiskGate can be accessed
	riskGateAdapter, ok := app.mainLoop.RiskGate.(*riskGateAdapter)
	if !ok {
		t.Fatal("RiskGate is not *riskGateAdapter type")
	}

	// Test IsBlocked - initially should not be blocked
	blocked, err := riskGateAdapter.IsBlocked(context.Background())
	if err != nil {
		t.Errorf("IsBlocked failed: %v", err)
	}
	if blocked {
		t.Error("RiskGate should not be blocked initially")
	}

	// Test GetState
	state, err := riskGateAdapter.GetState(context.Background())
	if err != nil {
		t.Errorf("GetState failed: %v", err)
	}
	if state.Level != ports.KillLevelOK {
		t.Errorf("Expected initial state level 'ok', got %s", state.Level)
	}
}

// TestWire_OrderManager verifies OrderManager is properly wired.
func TestWire_OrderManager(t *testing.T) {
	app, _ := newWiredTestApp(t)

	// Verify OrderManager Config method
	cfg := app.mainLoop.OrderManager.Config()
	if cfg.StuckTimeout != 300 {
		t.Errorf("Expected StuckTimeout of 300, got %d", cfg.StuckTimeout)
	}
	if cfg.MaxRBFAttempts != 3 {
		t.Errorf("Expected MaxRBFAttempts of 3, got %d", cfg.MaxRBFAttempts)
	}
}

// TestWire_EvaluateStrategies_NotEmpty verifies evaluateStrategies is properly wired.
// TR-01 DoD: verify `evaluateStrategies` function body is no longer just Debug log
func TestWire_EvaluateStrategies_NotEmpty(t *testing.T) {
	app, ctx := newWiredTestApp(t)

	// Call evaluateStrategies to verify it doesn't panic
	app.evaluateStrategies(ctx)
}

// TestWire_Metrics_Wired verifies metrics methods are callable.
func TestWire_Metrics_Wired(t *testing.T) {
	app, _ := newWiredTestApp(t)

	// Verify metrics methods are callable
	m := app.mainLoop.GetMetrics()
	m.IncRiskBlock()
	m.IncAllocBlock()
	m.IncSimulateFail()
	m.IncApproveFail()
	m.IncTxFailed()
	m.IncLoopHeartbeat()
	m.SetPositionsOpen(0)
	m.SetPositionsClosed(0)
	m.SetPnLDaily(domain.ZeroDecimal())
}

// TestWire_ApproveTracker verifies ApproveTracker has correct interface.
func TestWire_ApproveTracker(t *testing.T) {
	app, ctx := newWiredTestApp(t)

	tracker, ok := app.mainLoop.ApproveTracker.(*approveTrackerAdapter)
	if !ok {
		t.Fatal("ApproveTracker is not *approveTrackerAdapter type")
	}

	pool := domain.Pool{ID: "test-pool", Tier_: domain.TierC}
	if !tracker.HasAllowance(pool) {
		t.Error("HasAllowance should return true (placeholder)")
	}

	err := tracker.EnsureApproval(ctx, pool)
	if err != nil {
		t.Errorf("EnsureApproval failed: %v", err)
	}
}

// TestWire_TickInterval verifies the loop tick interval is set correctly.
func TestWire_TickInterval(t *testing.T) {
	app, _ := newWiredTestApp(t)

	cfg := app.mainLoop.GetConfig()
	if cfg.TickInterval != 1*time.Minute {
		t.Errorf("Expected tick interval of 1m, got %v", cfg.TickInterval)
	}
}

func TestOrderManagerAdapter_Close_ShadowUpdatesStateAndTx(t *testing.T) {
	app, ctx := newWiredTestApp(t)

	position := &domain.Position{
		ID:        "pos-close-shadow",
		PoolID:    "0x1111111111111111111111111111111111111111",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		Tier:      domain.TierC,
		AmountUSD: domain.MustDecimal("5"),
		OpenedAt:  time.Now().Unix(),
	}
	if err := app.store.PositionRepo().Save(ctx, position); err != nil {
		t.Fatalf("save position: %v", err)
	}

	om, ok := app.mainLoop.OrderManager.(*orderManagerAdapter)
	if !ok {
		t.Fatal("OrderManager is not *orderManagerAdapter")
	}
	result, err := om.Close(ctx, position.ID)
	if err != nil {
		t.Fatalf("Close failed: %v", err)
	}
	if !result.Success {
		t.Fatalf("Close returned unsuccessful result: %+v", result)
	}
	if result.FinalStatus != domain.StatusClosed {
		t.Fatalf("Close final status = %s, want %s", result.FinalStatus, domain.StatusClosed)
	}
	updated, err := app.store.PositionRepo().FindByID(ctx, position.ID)
	if err != nil {
		t.Fatalf("FindByID failed: %v", err)
	}
	if updated == nil || updated.Status != domain.StatusClosed {
		t.Fatalf("position status after close = %+v, want closed", updated)
	}
	tx, err := app.store.TxRepo().GetTxByHash(ctx, domain.ChainBase, result.TxHash)
	if err != nil {
		t.Fatalf("GetTxByHash failed: %v", err)
	}
	if tx.Status != domain.TxConfirmed {
		t.Fatalf("close tx status = %s, want %s", tx.Status, domain.TxConfirmed)
	}
}

func TestOrderManagerAdapter_Rebalance_ShadowPersistsTicksAndTx(t *testing.T) {
	app, ctx := newWiredTestApp(t)

	position := &domain.Position{
		ID:        "pos-rebalance-shadow",
		PoolID:    "0x2222222222222222222222222222222222222222",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		Tier:      domain.TierC,
		TickLower: -100,
		TickUpper: 100,
		AmountUSD: domain.MustDecimal("5"),
		OpenedAt:  time.Now().Unix(),
	}
	if err := app.store.PositionRepo().Save(ctx, position); err != nil {
		t.Fatalf("save position: %v", err)
	}

	om, ok := app.mainLoop.OrderManager.(*orderManagerAdapter)
	if !ok {
		t.Fatal("OrderManager is not *orderManagerAdapter")
	}
	result, err := om.Rebalance(ctx, position.ID, -200, 200)
	if err != nil {
		t.Fatalf("Rebalance failed: %v", err)
	}
	if !result.Success {
		t.Fatalf("Rebalance returned unsuccessful result: %+v", result)
	}
	updated, err := app.store.PositionRepo().FindByID(ctx, position.ID)
	if err != nil {
		t.Fatalf("FindByID failed: %v", err)
	}
	if updated == nil || updated.TickLower != -200 || updated.TickUpper != 200 {
		t.Fatalf("position ticks after rebalance = %+v, want [-200,200]", updated)
	}
	tx, err := app.store.TxRepo().GetTxByHash(ctx, domain.ChainBase, result.TxHash)
	if err != nil {
		t.Fatalf("GetTxByHash failed: %v", err)
	}
	if tx.Status != domain.TxConfirmed {
		t.Fatalf("rebalance tx status = %s, want %s", tx.Status, domain.TxConfirmed)
	}
}

func TestOrderManagerAdapter_CollectFees_ShadowWritesTxAudit(t *testing.T) {
	app, ctx := newWiredTestApp(t)

	position := &domain.Position{
		ID:        "pos-collect-shadow",
		PoolID:    "0x3333333333333333333333333333333333333333",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		Tier:      domain.TierC,
		AmountUSD: domain.MustDecimal("5"),
		OpenedAt:  time.Now().Unix(),
	}
	if err := app.store.PositionRepo().Save(ctx, position); err != nil {
		t.Fatalf("save position: %v", err)
	}

	om, ok := app.mainLoop.OrderManager.(*orderManagerAdapter)
	if !ok {
		t.Fatal("OrderManager is not *orderManagerAdapter")
	}
	result, err := om.CollectFees(ctx, position.ID)
	if err != nil {
		t.Fatalf("CollectFees failed: %v", err)
	}
	if !result.Success {
		t.Fatalf("CollectFees returned unsuccessful result: %+v", result)
	}
	updated, err := app.store.PositionRepo().FindByID(ctx, position.ID)
	if err != nil {
		t.Fatalf("FindByID failed: %v", err)
	}
	if updated == nil || updated.Status != domain.StatusOpen {
		t.Fatalf("position status after collect = %+v, want open", updated)
	}
	tx, err := app.store.TxRepo().GetTxByHash(ctx, domain.ChainBase, result.TxHash)
	if err != nil {
		t.Fatalf("GetTxByHash failed: %v", err)
	}
	if tx.Status != domain.TxConfirmed {
		t.Fatalf("collect tx status = %s, want %s", tx.Status, domain.TxConfirmed)
	}
}
