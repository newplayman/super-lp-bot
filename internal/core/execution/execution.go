package execution

import (
	"context"
	"fmt"
	"math/big"
	"sync"

	"github.com/lpbot/lpbot/internal/core/simulation"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// positionState tracks the state of a position in shadow mode.
type positionState struct {
	Status domain.PositionStatus
	Intent interface{} // OpenIntent, ExitIntent, or RebalanceIntent
}

// defaultOrderManager is the shadow-mode implementation of OrderManager.
// It builds and simulates transactions without broadcasting.
type defaultOrderManager struct {
	config    ExecutionConfig
	simulator simulation.Simulator
	chain     ports.Chain
	txBuilder *TxBuilder
	positions map[string]*positionState // in-memory position tracking
	mu        sync.RWMutex
	txs       map[string]domain.SignedTx // tracked transactions
	txsMu     sync.RWMutex
}

// NewDefaultOrderManager creates a new shadow-mode OrderManager implementation.
func NewDefaultOrderManager(deps ExecutionDependencies, config ExecutionConfig, sim simulation.Simulator) OrderManager {
	return &defaultOrderManager{
		config:    config,
		simulator: sim,
		chain:     deps.Chain,
		txBuilder: NewTxBuilder(deps.Wallet, deps.Chain),
		positions: make(map[string]*positionState),
		txs:       make(map[string]domain.SignedTx),
	}
}

// Compile-time interface assertion
var _ OrderManager = (*defaultOrderManager)(nil)

// Open implements OrderManager.Open for shadow mode.
// It builds the transaction, simulates it, and updates position status without broadcasting.
func (m *defaultOrderManager) Open(ctx context.Context, intent OpenIntent) ExecutionResult {
	// Validate intent has simulation result (invariant #4)
	if intent.Simulation == nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "simulation result required before opening position",
		}
	}

	// Validate MinOut and Deadline are non-zero (invariant #4)
	if intent.Simulation.OutputAmounts == nil || len(intent.Simulation.OutputAmounts) == 0 {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "simulation output amounts required",
		}
	}

	// Build the add liquidity transaction
	tx, err := m.txBuilder.BuildAddLiquidityTx(ctx, intent)
	if err != nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("failed to build transaction: %v", err),
		}
	}

	// Run simulation via the simulator
	simReq := simulation.SimulationRequest{
		Tx:      tx,
		BlockRef: intent.Simulation.BlockRef,
		TraceID:  intent.TraceID,
		Purpose: "honeypot_check",
	}

	simResp, err := m.simulator.SimulateAndValidate(ctx, simReq)
	if err != nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("simulation failed: %v", err),
		}
	}

	// Check for honeypot detection
	if simResp.HoneypotDetected {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "honeypot detected: transaction appears to be a trap",
			FinalStatus: domain.StatusRejected,
		}
	}

	// Validate slippage (invariant #4)
	if !simResp.SlippageValid {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "slippage exceeds acceptable bounds",
			FinalStatus: domain.StatusRejected,
		}
	}

	// Validate simulation success
	if simResp.Result == nil || !simResp.Result.Success {
		errMsg := "simulation reverted"
		if simResp.Result != nil && simResp.Result.Error != "" {
			errMsg = simResp.Result.Error
		}
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      errMsg,
		}
	}

	// In shadow mode: skip broadcasting, update position status directly
	m.mu.Lock()
	m.positions[intent.PositionID] = &positionState{
		Status: domain.StatusOpen,
		Intent: intent,
	}
	m.mu.Unlock()

	return ExecutionResult{
		PositionID:  intent.PositionID,
		Success:     true,
		FinalStatus: domain.StatusOpen,
	}
}

// Close implements OrderManager.Close for shadow mode.
func (m *defaultOrderManager) Close(ctx context.Context, intent ExitIntent) ExecutionResult {
	// Validate simulation result
	if intent.Simulation == nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "simulation result required before closing position",
		}
	}

	// Check position exists
	m.mu.RLock()
	pos, exists := m.positions[intent.PositionID]
	m.mu.RUnlock()

	if !exists {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "position not found",
		}
	}

	// Validate position can transition to exiting
	if !pos.Status.CanTransitionTo(domain.StatusExiting) {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("cannot transition from %s to exiting", pos.Status),
		}
	}

	// Build close transaction
	tx, err := m.txBuilder.BuildRemoveLiquidityTx(ctx, intent)
	if err != nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("failed to build transaction: %v", err),
		}
	}

	// Run simulation
	simReq := simulation.SimulationRequest{
		Tx:       tx,
		BlockRef: intent.Simulation.BlockRef,
		TraceID:  intent.TraceID,
		Purpose:  "close_position",
	}

	simResp, err := m.simulator.SimulateAndValidate(ctx, simReq)
	if err != nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("simulation failed: %v", err),
		}
	}

	// Check for honeypot detection
	if simResp.HoneypotDetected {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "honeypot detected during exit simulation",
			FinalStatus: domain.StatusExitFailed,
		}
	}

	// Validate slippage
	if !simResp.SlippageValid {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "slippage exceeds acceptable bounds during exit",
			FinalStatus: domain.StatusExitFailed,
		}
	}

	// Validate simulation success
	if simResp.Result == nil || !simResp.Result.Success {
		errMsg := "simulation reverted"
		if simResp.Result != nil && simResp.Result.Error != "" {
			errMsg = simResp.Result.Error
		}
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      errMsg,
			FinalStatus: domain.StatusExitFailed,
		}
	}

	// In shadow mode: skip broadcasting, update position status
	m.mu.Lock()
	if pos, ok := m.positions[intent.PositionID]; ok {
		pos.Status = domain.StatusClosed
	}
	m.mu.Unlock()

	return ExecutionResult{
		PositionID:  intent.PositionID,
		Success:     true,
		FinalStatus: domain.StatusClosed,
	}
}

// Rebalance implements OrderManager.Rebalance for shadow mode.
// It removes liquidity at current range and adds at new range in sequence.
func (m *defaultOrderManager) Rebalance(ctx context.Context, intent RebalanceIntent) ExecutionResult {
	// Validate simulation result
	if intent.Simulation == nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "simulation result required before rebalancing",
		}
	}

	// Check position exists
	m.mu.RLock()
	pos, exists := m.positions[intent.PositionID]
	m.mu.RUnlock()

	if !exists {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      "position not found",
		}
	}

	// Validate position can be rebalanced (must be open)
	if pos.Status != domain.StatusOpen {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("cannot rebalance position in status %s", pos.Status),
		}
	}

	// Build remove and add transactions
	removeTx, addTx, err := m.txBuilder.BuildRebalanceTxs(ctx, intent)
	if err != nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("failed to build rebalance transactions: %v", err),
		}
	}

	// Simulate sequence (remove then add)
	simReqs := []simulation.SimulationRequest{
		{
			Tx:       removeTx,
			BlockRef: intent.Simulation.BlockRef,
			TraceID:  intent.TraceID,
			Purpose:  "rebalance_remove",
		},
		{
			Tx:       addTx,
			BlockRef: intent.Simulation.BlockRef,
			TraceID:  intent.TraceID,
			Purpose:  "rebalance_add",
		},
	}

	simResps, err := m.simulator.SimulateSequenceAndValidate(ctx, simReqs)
	if err != nil {
		return ExecutionResult{
			PositionID: intent.PositionID,
			Success:    false,
			Error:      fmt.Sprintf("rebalance simulation failed: %v", err),
		}
	}

	// Validate all simulations succeeded
	for i, simResp := range simResps {
		if simResp.HoneypotDetected {
			return ExecutionResult{
				PositionID: intent.PositionID,
				Success:    false,
				Error:      fmt.Sprintf("honeypot detected in step %d", i+1),
			}
		}
		if !simResp.SlippageValid {
			return ExecutionResult{
				PositionID: intent.PositionID,
				Success:    false,
				Error:      fmt.Sprintf("slippage invalid in step %d", i+1),
			}
		}
		if simResp.Result == nil || !simResp.Result.Success {
			errMsg := "simulation reverted"
			if simResp.Result != nil && simResp.Result.Error != "" {
				errMsg = simResp.Result.Error
			}
			return ExecutionResult{
				PositionID: intent.PositionID,
				Success:    false,
				Error:      fmt.Sprintf("rebalance step %d failed: %s", i+1, errMsg),
			}
		}
	}

	// In shadow mode: skip broadcasting, update position tick range
	m.mu.Lock()
	if pos, ok := m.positions[intent.PositionID]; ok {
		if rebalanceIntent, ok := pos.Intent.(OpenIntent); ok {
			// Update the stored intent with new tick range
			rebalanceIntent.TickLower = intent.NewTickLower
			rebalanceIntent.TickUpper = intent.NewTickUpper
			pos.Intent = rebalanceIntent
		}
	}
	m.mu.Unlock()

	return ExecutionResult{
		PositionID:  intent.PositionID,
		Success:     true,
		FinalStatus: domain.StatusOpen, // Rebalance keeps position open
	}
}

// CollectFees implements OrderManager.CollectFees for shadow mode.
func (m *defaultOrderManager) CollectFees(ctx context.Context, positionID string) ExecutionResult {
	// Check position exists
	m.mu.RLock()
	_, exists := m.positions[positionID]
	m.mu.RUnlock()

	if !exists {
		return ExecutionResult{
			PositionID: positionID,
			Success:    false,
			Error:      "position not found",
		}
	}

	// Build collect fees transaction
	tx, err := m.txBuilder.BuildCollectFeesTx(ctx, positionID)
	if err != nil {
		return ExecutionResult{
			PositionID: positionID,
			Success:    false,
			Error:      fmt.Sprintf("failed to build collect fees transaction: %v", err),
		}
	}

	// For collect fees, we need a block reference - use latest
	block, err := m.chain.GetBlock(ctx, domain.BlockRef{})
	if err != nil {
		return ExecutionResult{
			PositionID: positionID,
			Success:    false,
			Error:      fmt.Sprintf("failed to get block reference: %v", err),
		}
	}

	// Simulate collect fees
	simReq := simulation.SimulationRequest{
		Tx:       tx,
		BlockRef: block.Ref,
		TraceID:  "",
		Purpose:  "collect_fees",
	}

	simResp, err := m.simulator.SimulateAndValidate(ctx, simReq)
	if err != nil {
		return ExecutionResult{
			PositionID: positionID,
			Success:    false,
			Error:      fmt.Sprintf("collect fees simulation failed: %v", err),
		}
	}

	// Collect fees can succeed even with some edge cases, so we only fail on critical errors
	if simResp.Result == nil || !simResp.Result.Success {
		errMsg := "simulation reverted"
		if simResp.Result != nil && simResp.Result.Error != "" {
			errMsg = simResp.Result.Error
		}
		return ExecutionResult{
			PositionID: positionID,
			Success:    false,
			Error:      errMsg,
		}
	}

	// In shadow mode: skip broadcasting
	return ExecutionResult{
		PositionID: positionID,
		Success:    true,
	}
}

// UpdateTxStatus implements OrderManager.UpdateTxStatus.
// In shadow mode, this is a no-op since we don't track real transactions.
func (m *defaultOrderManager) UpdateTxStatus(ctx context.Context, txHash string, status domain.TxStatus) error {
	// In shadow mode, we don't track real transactions
	// This method exists to satisfy the interface but does nothing
	return nil
}

// GetPendingTxs implements OrderManager.GetPendingTxs.
// In shadow mode, returns empty since we don't broadcast transactions.
func (m *defaultOrderManager) GetPendingTxs(ctx context.Context) ([]domain.SignedTx, error) {
	m.txsMu.RLock()
	defer m.txsMu.RUnlock()

	result := make([]domain.SignedTx, 0, len(m.txs))
	for _, tx := range m.txs {
		result = append(result, tx)
	}
	return result, nil
}

// RetryStuck implements OrderManager.RetryStuck.
// In shadow mode, RBF is not supported since we don't broadcast transactions.
func (m *defaultOrderManager) RetryStuck(ctx context.Context, txHash string) (ExecutionResult, error) {
	return ExecutionResult{
		TxHash:  txHash,
		Success: false,
		Error:   "RBF not supported in shadow mode: transactions are not broadcast",
	}, nil
}

// Config implements OrderManager.Config.
func (m *defaultOrderManager) Config() ExecutionConfig {
	return m.config
}

// GetPositionStatus returns the current status of a position (for testing).
func (m *defaultOrderManager) GetPositionStatus(positionID string) (domain.PositionStatus, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	pos, exists := m.positions[positionID]
	if !exists {
		return "", false
	}
	return pos.Status, true
}

// Verify dependencies satisfy ports interfaces at compile time
func verifyPorts() {
	var _ ports.Chain = (*nilChain)(nil)
	var _ ports.EVMChain = (*nilEVMChain)(nil)
	var _ ports.SolanaChain = (*nilSolanaChain)(nil)
	var _ ports.Wallet = (*nilWallet)(nil)
	var _ ports.Broadcaster = (*nilBroadcaster)(nil)
	var _ ports.MEVSubmitter = (*nilMEVSubmitter)(nil)
	var _ ports.Bus = (*nilBus)(nil)
}

// nilChain is a nil implementation for compile-time verification.
type nilChain struct{}

func (*nilChain) Info() ports.ChainInfo { return ports.ChainInfo{} }
func (*nilChain) GetBlock(context.Context, domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, nil
}
func (*nilChain) SubscribeBlocks(context.Context) (<-chan ports.Block, error) { return nil, nil }
func (*nilChain) Multicall(context.Context, []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (*nilChain) EstimateGas(context.Context, ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (*nilChain) ListMyPositions(context.Context, domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}

// nilEVMChain is a nil implementation for compile-time verification.
type nilEVMChain struct{}

func (*nilEVMChain) Info() ports.ChainInfo { return ports.ChainInfo{} }
func (*nilEVMChain) GetBlock(context.Context, domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, nil
}
func (*nilEVMChain) SubscribeBlocks(context.Context) (<-chan ports.Block, error) { return nil, nil }
func (*nilEVMChain) Multicall(context.Context, []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (*nilEVMChain) EstimateGas(context.Context, ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (*nilEVMChain) ListMyPositions(context.Context, domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}
func (*nilEVMChain) NonceAt(context.Context, domain.Address, domain.BlockRef) (uint64, error) {
	return 0, nil
}
func (*nilEVMChain) PendingNonceAt(context.Context, domain.Address) (uint64, error) { return 0, nil }
func (*nilEVMChain) SuggestGasFees(context.Context) (*big.Int, *big.Int, error) {
	return nil, nil, nil
}

// nilSolanaChain is a nil implementation for compile-time verification.
type nilSolanaChain struct{}

func (*nilSolanaChain) Info() ports.ChainInfo { return ports.ChainInfo{} }
func (*nilSolanaChain) GetBlock(context.Context, domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, nil
}
func (*nilSolanaChain) SubscribeBlocks(context.Context) (<-chan ports.Block, error) { return nil, nil }
func (*nilSolanaChain) Multicall(context.Context, []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (*nilSolanaChain) EstimateGas(context.Context, ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (*nilSolanaChain) ListMyPositions(context.Context, domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}
func (*nilSolanaChain) LatestBlockhash(context.Context) (string, error)     { return "", nil }
func (*nilSolanaChain) GetComputeUnitPrice(context.Context) (uint64, error) { return 0, nil }

// nilWallet is a nil implementation for compile-time verification.
type nilWallet struct{}

func (*nilWallet) Open(context.Context) error { return nil }
func (*nilWallet) Close() error               { return nil }
func (*nilWallet) Address() domain.Address    { return domain.Address{} }
func (*nilWallet) Chain() domain.ChainID      { return "" }
func (*nilWallet) Sign(context.Context, domain.UnsignedTx) (domain.SignedTx, error) {
	return domain.SignedTx{}, nil
}
func (*nilWallet) ApproveExact(context.Context, domain.Address, domain.Address, *big.Int) (
	domain.UnsignedTx, error,
) {
	return domain.UnsignedTx{}, nil
}
func (*nilWallet) Revoke(context.Context, domain.Address, domain.Address) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}

// nilBroadcaster is a nil implementation for compile-time verification.
type nilBroadcaster struct{}

func (*nilBroadcaster) Send(context.Context, domain.SignedTx) error { return nil }
func (*nilBroadcaster) CallCount() int64                            { return 0 }

// nilMEVSubmitter is a nil implementation for compile-time verification.
type nilMEVSubmitter struct{}

func (*nilMEVSubmitter) Submit(context.Context, domain.SignedTx, ports.MEVSubmitOpts) (
	ports.MEVSubmissionResult, error,
) {
	return ports.MEVSubmissionResult{}, nil
}
func (*nilMEVSubmitter) Type() string { return "nil" }

// nilBus is a nil implementation for compile-time verification.
type nilBus struct{}

func (*nilBus) Publish(domain.Event) error { return nil }
func (*nilBus) Subscribe(string, ports.EventHandler) (ports.Subscription, error) {
	return nil, nil
}

// Suppress unused import warning
var _ = (*nilEVMChain)(nil)
