package execution

import (
	"context"
	"fmt"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// defaultExecution is the scaffold stub implementation that panics on use.
// Real implementation will be added in later phases (Phase 2 shadow, Phase 3 live).
//
// In Phase 0, this stub exists only to establish the interface contract
// and allow other modules to compile. Usage in production will panic.
type defaultExecution struct {
	deps  ExecutionDependencies
	config ExecutionConfig
}

// NewDefaultExecution creates a new scaffold execution implementation.
// This implementation panics on any method call to prevent accidental use.
//
// Real execution logic will be implemented in Phase 2 (shadow) and Phase 3 (live).
// Until then, any attempt to use this executor will panic with a helpful message.
func NewDefaultExecution(deps ExecutionDependencies, config ExecutionConfig) OrderManager {
	return &defaultExecution{
		deps:   deps,
		config: config,
	}
}

// Open implements OrderManager.Open with a panic stub.
func (e *defaultExecution) Open(_ context.Context, intent OpenIntent) ExecutionResult {
	panic(fmt.Sprintf("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: "+
		"Open position %s on %s", intent.PositionID, intent.Chain))
}

// Close implements OrderManager.Close with a panic stub.
func (e *defaultExecution) Close(_ context.Context, intent ExitIntent) ExecutionResult {
	panic(fmt.Sprintf("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: "+
		"Close position %s on %s", intent.PositionID, intent.Chain))
}

// Rebalance implements OrderManager.Rebalance with a panic stub.
func (e *defaultExecution) Rebalance(_ context.Context, intent RebalanceIntent) ExecutionResult {
	panic(fmt.Sprintf("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: "+
		"Rebalance position %s on %s", intent.PositionID, intent.Chain))
}

// CollectFees implements OrderManager.CollectFees with a panic stub.
func (e *defaultExecution) CollectFees(_ context.Context, positionID string) ExecutionResult {
	panic(fmt.Sprintf("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: "+
		"CollectFees for position %s", positionID))
}

// UpdateTxStatus implements OrderManager.UpdateTxStatus with a panic stub.
func (e *defaultExecution) UpdateTxStatus(_ context.Context, txHash string, status domain.TxStatus) error {
	panic(fmt.Sprintf("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: "+
		"UpdateTxStatus %s -> %s", txHash, status))
}

// GetPendingTxs implements OrderManager.GetPendingTxs with a panic stub.
func (e *defaultExecution) GetPendingTxs(_ context.Context) ([]domain.SignedTx, error) {
	panic("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: GetPendingTxs")
}

// RetryStuck implements OrderManager.RetryStuck with a panic stub.
func (e *defaultExecution) RetryStuck(_ context.Context, txHash string) (ExecutionResult, error) {
	panic(fmt.Sprintf("execution: defaultExecution is a scaffold stub; real implementation pending Phase 2-3: "+
		"RetryStuck %s", txHash))
}

// Config implements OrderManager.Config.
func (e *defaultExecution) Config() ExecutionConfig {
	return e.config
}

// Compile-time interface assertions
var _ OrderManager = (*defaultExecution)(nil)

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

func (*nilChain) Info() ports.ChainInfo                                          { return ports.ChainInfo{} }
func (*nilChain) GetBlock(context.Context, domain.BlockRef) (ports.Block, error) { return ports.Block{}, nil }
func (*nilChain) SubscribeBlocks(context.Context) (<-chan ports.Block, error)     { return nil, nil }
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

func (*nilEVMChain) Info() ports.ChainInfo                                          { return ports.ChainInfo{} }
func (*nilEVMChain) GetBlock(context.Context, domain.BlockRef) (ports.Block, error) { return ports.Block{}, nil }
func (*nilEVMChain) SubscribeBlocks(context.Context) (<-chan ports.Block, error)    { return nil, nil }
func (*nilEVMChain) Multicall(context.Context, []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (*nilEVMChain) EstimateGas(context.Context, ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (*nilEVMChain) ListMyPositions(context.Context, domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}
func (*nilEVMChain) NonceAt(context.Context, domain.Address, domain.BlockRef) (uint64, error) { return 0, nil }
func (*nilEVMChain) PendingNonceAt(context.Context, domain.Address) (uint64, error)           { return 0, nil }
func (*nilEVMChain) SuggestGasFees(context.Context) (*big.Int, *big.Int, error) {
	return nil, nil, nil
}

// nilSolanaChain is a nil implementation for compile-time verification.
type nilSolanaChain struct{}

func (*nilSolanaChain) Info() ports.ChainInfo                                          { return ports.ChainInfo{} }
func (*nilSolanaChain) GetBlock(context.Context, domain.BlockRef) (ports.Block, error) { return ports.Block{}, nil }
func (*nilSolanaChain) SubscribeBlocks(context.Context) (<-chan ports.Block, error)    { return nil, nil }
func (*nilSolanaChain) Multicall(context.Context, []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (*nilSolanaChain) EstimateGas(context.Context, ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (*nilSolanaChain) ListMyPositions(context.Context, domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}
func (*nilSolanaChain) LatestBlockhash(context.Context) (string, error)              { return "", nil }
func (*nilSolanaChain) GetComputeUnitPrice(context.Context) (uint64, error)           { return 0, nil }

// nilWallet is a nil implementation for compile-time verification.
type nilWallet struct{}

func (*nilWallet) Open(context.Context) error                        { return nil }
func (*nilWallet) Close() error                                      { return nil }
func (*nilWallet) Address() domain.Address                           { return domain.Address{} }
func (*nilWallet) Chain() domain.ChainID                            { return "" }
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
func (*nilBroadcaster) CallCount() int64                           { return 0 }

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

func (*nilBus) Publish(domain.Event) error                              { return nil }
func (*nilBus) Subscribe(string, ports.EventHandler) (ports.Subscription, error) {
	return nil, nil
}

// Suppress unused import warning
var _ = (*nilEVMChain)(nil)