// Package loop implements the main trading loop with risk gates and allocation checks.
package loop

import (
	"context"
	"time"

	"github.com/shopspring/decimal"

	"github.com/lpbot/lpbot/internal/domain"
	riskcore "github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/ports"
)

// MainLoopConfig holds configuration for the main loop.
type MainLoopConfig struct {
	TickInterval       time.Duration
	Broadcaster        ports.Broadcaster
	RiskGate           RiskGate
	AllocationManager  AllocationManager
	Simulator          ports.Simulator
	ApproveTracker     ApproveTracker
	OrderManager       OrderManager
	Scanner            Scanner
	Metrics            Metrics
}

// Metrics defines the metrics interface for the loop.
type Metrics interface {
	IncRiskBlock()
	IncAllocBlock()
	IncSimulateFail()
	IncApproveFail()
	IncTxFailed()
	IncLoopHeartbeat()
	SetPositionsOpen(n int64)
	SetPositionsClosed(n int64)
	SetPnLDaily(pnl decimal.Decimal)
}

// RiskGate defines the risk gate interface.
type RiskGate interface {
	IsBlocked(ctx context.Context) (bool, error)
	CheckVaR(ctx context.Context, totalValue, realizedLoss decimal.Decimal) (ports.KillLevel, error)
	CheckDrawdown(ctx context.Context, peakValue, currentValue decimal.Decimal, isWeekly bool) (ports.KillLevel, error)
	CheckExposure(ctx context.Context, totalExposure, totalBudget decimal.Decimal) (ports.KillLevel, error)
	GetState(ctx context.Context) (ports.KillState, error)
	RaiseKill(ctx context.Context, reason string) error
	LowerWarn(ctx context.Context) error
	RecordRiskEvent(ctx context.Context, event ports.RiskEvent) error
	RecordTxFailure(ctx context.Context, poolKey string)
}

// AllocationManager defines the allocation manager interface.
type AllocationManager interface {
	CheckAllocation(tier domain.Tier, amount decimal.Decimal) bool
	CheckTotalExposure(current, budget decimal.Decimal) bool
	GetRemainingBudget(tier domain.Tier, current decimal.Decimal) decimal.Decimal
}

type snapshotAllocationManager interface {
	CheckAllocationWithSnapshot(ctx context.Context, c riskcore.AllocationCandidate) (bool, riskcore.AllocReason)
	CheckTotalExposureWithSnapshot(ctx context.Context, c riskcore.AllocationCandidate) (bool, riskcore.AllocReason)
}

// ApproveTracker defines the approve tracker interface.
type ApproveTracker interface {
	HasAllowance(pool domain.Pool) bool
	EnsureApproval(ctx context.Context, pool domain.Pool) error
}

// OrderManager defines the order manager interface.
type OrderManager interface {
	Open(ctx context.Context, pool domain.Pool, amountUSD decimal.Decimal) (ExecutionResult, error)
	Close(ctx context.Context, positionID string) (ExecutionResult, error)
	Rebalance(ctx context.Context, positionID string, newLower, newUpper int64) (ExecutionResult, error)
	CollectFees(ctx context.Context, positionID string) (ExecutionResult, error)
	OnTxFailure(ctx context.Context, positionID string)
	Config() ExecutionConfig
}

// ExecutionConfig holds configuration for order manager.
type ExecutionConfig struct {
	StuckTimeout          int
	MaxRBFAttempts        int
	RequiredConfirmations int
}

// ExecutionResult holds the result of an execution attempt.
type ExecutionResult struct {
	TxHash      string
	Success     bool
	Error       string
	PositionID  string
	FinalStatus domain.PositionStatus
}

// Scanner defines the scanner interface.
type Scanner interface {
	Run(ctx context.Context) error
}

// MainLoop orchestrates the main trading loop.
type MainLoop struct {
	config            MainLoopConfig
	Broadcaster       ports.Broadcaster
	RiskGate          RiskGate
	AllocationManager AllocationManager
	Simulator          ports.Simulator
	ApproveTracker     ApproveTracker
	OrderManager       OrderManager
	Scanner            Scanner
	metrics            Metrics
}

// NewMainLoop creates a new MainLoop instance.
func NewMainLoop(cfg MainLoopConfig) *MainLoop {
	if cfg.TickInterval == 0 {
		cfg.TickInterval = 1 * time.Minute
	}
	metrics := cfg.Metrics
	if metrics == nil {
		metrics = &noopMetrics{}
	}
	return &MainLoop{
		config:            cfg,
		Broadcaster:       cfg.Broadcaster,
		RiskGate:          cfg.RiskGate,
		AllocationManager: cfg.AllocationManager,
		Simulator:         cfg.Simulator,
		ApproveTracker:    cfg.ApproveTracker,
		OrderManager:      cfg.OrderManager,
		Scanner:           cfg.Scanner,
		metrics:           metrics,
	}
}

// noopMetrics implements Metrics with no-op operations.
type noopMetrics struct{}

func (m *noopMetrics) IncRiskBlock()                      {}
func (m *noopMetrics) IncAllocBlock()                     {}
func (m *noopMetrics) IncSimulateFail()                   {}
func (m *noopMetrics) IncApproveFail()                    {}
func (m *noopMetrics) IncTxFailed()                       {}
func (m *noopMetrics) IncLoopHeartbeat()                  {}
func (m *noopMetrics) SetPositionsOpen(n int64)          {}
func (m *noopMetrics) SetPositionsClosed(n int64)        {}
func (m *noopMetrics) SetPnLDaily(pnl decimal.Decimal)   {}

// Run starts the main loop with the given context.
// It stops when the context is cancelled.
func (ml *MainLoop) Run(ctx context.Context) {
	ticker := time.NewTicker(ml.config.TickInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			ml.evaluateStrategies(ctx)
		}
	}
}

// evaluateStrategies evaluates candidate pools from the scanner.
// This is the main strategy evaluation tick function.
func (ml *MainLoop) evaluateStrategies(ctx context.Context) {
	ml.metrics.IncLoopHeartbeat()
}

// EvaluatePool evaluates a single pool for trading opportunity.
// Returns true if the pool is allowed through all risk gates.
// This is the core fail-closed pipeline.
func (ml *MainLoop) EvaluatePool(ctx context.Context, pool domain.Pool) (bool, error) {
	// Step 1: Check RiskGate (fail-closed) - if blocked, no trading
	blocked, err := ml.RiskGate.IsBlocked(ctx)
	if err != nil {
		return false, err
	}
	if blocked {
		ml.metrics.IncRiskBlock()
		return false, nil
	}

	// Step 2: Check per-pool allocation limit (fail-closed)
	// Get the max per-pool amount for this tier
	thresholds := domain.TierThresholdsFor(pool.Tier_)
	amount := thresholds.MaxPerPoolUSD
	candidate := riskcore.AllocationCandidate{
		PoolID:    pool.ID,
		Chain:     pool.Chain,
		Tier:      pool.Tier_,
		AmountUSD: amount,
	}
	if snapshotMgr, ok := ml.AllocationManager.(snapshotAllocationManager); ok {
		allowed, _ := snapshotMgr.CheckAllocationWithSnapshot(ctx, candidate)
		if !allowed {
			ml.metrics.IncAllocBlock()
			return false, nil
		}
	} else if !ml.AllocationManager.CheckAllocation(pool.Tier_, amount) {
		ml.metrics.IncAllocBlock()
		return false, nil
	}
	if snapshotMgr, ok := ml.AllocationManager.(snapshotAllocationManager); ok {
		allowed, _ := snapshotMgr.CheckTotalExposureWithSnapshot(ctx, candidate)
		if !allowed {
			ml.metrics.IncAllocBlock()
			return false, nil
		}
	} else if !ml.AllocationManager.CheckTotalExposure(amount, decimal.NewFromInt(1000)) {
		ml.metrics.IncAllocBlock()
		return false, nil
	}

	// Step 3: Simulate the transaction (fail-closed on simulation failure)
	// For simulation, we use empty tx and block ref as placeholders
	// In real implementation, these would be populated from the pool
	sim, err := ml.Simulator.Simulate(ctx, domain.UnsignedTx{}, domain.BlockRef{})
	if err != nil {
		ml.metrics.IncSimulateFail()
		return false, nil
	}
	if !sim.Success {
		ml.metrics.IncSimulateFail()
		return false, nil
	}

	// Step 4: Ensure approval (fail-closed on approval failure)
	if !ml.ApproveTracker.HasAllowance(pool) {
		if err := ml.ApproveTracker.EnsureApproval(ctx, pool); err != nil {
			ml.metrics.IncApproveFail()
			return false, nil
		}
	}

	// Step 5: Submit order via OrderManager
	thresholds = domain.TierThresholdsFor(pool.Tier_)
	result, err := ml.OrderManager.Open(ctx, pool, thresholds.MaxPerPoolUSD)
	if err != nil || !result.Success {
		ml.metrics.IncTxFailed()
		// Feedback to RiskGate on transaction failure
		ml.OrderManager.OnTxFailure(ctx, pool.ID)
		return false, nil
	}

	return true, nil
}

// GetMetrics returns the current metrics.
func (ml *MainLoop) GetMetrics() Metrics {
	return ml.metrics
}

// GetConfig returns the main loop configuration.
func (ml *MainLoop) GetConfig() MainLoopConfig {
	return ml.config
}
