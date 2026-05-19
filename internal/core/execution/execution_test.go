package execution_test

import (
	"context"
	"errors"
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/internal/core/execution"
	"github.com/lpbot/lpbot/internal/core/simulation"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// ErrSimulationFailed is a sentinel error for simulation failures in tests.
var ErrSimulationFailed = errors.New("simulation failed")

// mockWallet is a mock implementation of ports.Wallet.
type mockWallet struct {
	address domain.Address
	chain   domain.ChainID
}

func (m *mockWallet) Open(ctx context.Context) error { return nil }
func (m *mockWallet) Close() error                  { return nil }
func (m *mockWallet) Address() domain.Address        { return m.address }
func (m *mockWallet) Chain() domain.ChainID          { return m.chain }
func (m *mockWallet) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	return domain.SignedTx{UnsignedTx: tx, Hash: "mock-hash"}, nil
}
func (m *mockWallet) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (
	domain.UnsignedTx, error,
) {
	return domain.UnsignedTx{}, nil
}
func (m *mockWallet) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}

// mockChain is a mock implementation of ports.Chain.
type mockChain struct {
	info ports.ChainInfo
}

func (m *mockChain) Info() ports.ChainInfo                                     { return m.info }
func (m *mockChain) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	return ports.Block{Ref: domain.BlockRef{Chain: domain.ChainBase, Number: 1}}, nil
}
func (m *mockChain) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) { return nil, nil }
func (m *mockChain) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (m *mockChain) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (m *mockChain) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}

// mockSimulator is a mock implementation of simulation.Simulator.
type mockSimulator struct {
	simulateFunc         func(ctx context.Context, req simulation.SimulationRequest) (*simulation.SimulationResponse, error)
	simulateSequenceFunc func(ctx context.Context, reqs []simulation.SimulationRequest) ([]simulation.SimulationResponse, error)
}

func (m *mockSimulator) SimulateAndValidate(ctx context.Context, req simulation.SimulationRequest) (*simulation.SimulationResponse, error) {
	if m.simulateFunc != nil {
		return m.simulateFunc(ctx, req)
	}
	return &simulation.SimulationResponse{
		Result: &domain.SimulationResult{
			Success:      true,
			GasUsed:      150000,
			OutputAmounts: []domain.TokenAmount{},
		},
		HoneypotDetected: false,
		SlippageValid:    true,
	}, nil
}

func (m *mockSimulator) SimulateSequenceAndValidate(ctx context.Context, reqs []simulation.SimulationRequest) ([]simulation.SimulationResponse, error) {
	if m.simulateSequenceFunc != nil {
		return m.simulateSequenceFunc(ctx, reqs)
	}
	results := make([]simulation.SimulationResponse, len(reqs))
	for i := range reqs {
		results[i] = simulation.SimulationResponse{
			Result: &domain.SimulationResult{
				Success:      true,
				GasUsed:      150000,
				OutputAmounts: []domain.TokenAmount{},
			},
			HoneypotDetected: false,
			SlippageValid:    true,
		}
	}
	return results, nil
}

func TestOrderManager_Open_Success(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	// Create simulator with success response
	sim := &mockSimulator{}

	om := execution.NewDefaultOrderManager(deps, config, sim)

	intent := execution.OpenIntent{
		PositionID: "pos-1",
		PoolID:     "pool-1",
		Chain:      "base",
		Tier:       domain.TierC,
		AmountUSD:  domain.MustDecimal("50"),
		TickLower:  100,
		TickUpper:  200,
		TraceID:    "trace-123",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{
				Chain:    domain.ChainBase,
				Number:   1,
			},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), Symbol: "ETH", Decimals: 18}, Amount: domain.MustDecimal("1")},
			},
		},
	}

	result := om.Open(ctx, intent)

	if !result.Success {
		t.Errorf("Expected Open to succeed, got error: %s", result.Error)
	}
	if result.FinalStatus != domain.StatusOpen {
		t.Errorf("Expected final status to be %s, got %s", domain.StatusOpen, result.FinalStatus)
	}
	if result.PositionID != "pos-1" {
		t.Errorf("Expected position ID to be pos-1, got %s", result.PositionID)
	}
}

func TestOrderManager_Open_HoneypotDetected(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	// Create simulator that returns honeypot detected
	sim := &mockSimulator{
		simulateFunc: func(ctx context.Context, req simulation.SimulationRequest) (*simulation.SimulationResponse, error) {
			return &simulation.SimulationResponse{
				Result: &domain.SimulationResult{
					Success: true,
					OutputAmounts: []domain.TokenAmount{},
				},
				HoneypotDetected: true,
				SlippageValid:    true,
			}, nil
		},
	}

	om := execution.NewDefaultOrderManager(deps, config, sim)

	intent := execution.OpenIntent{
		PositionID: "pos-honeypot",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}

	result := om.Open(ctx, intent)

	if result.Success {
		t.Error("Expected Open to fail when honeypot is detected")
	}
	if result.FinalStatus != domain.StatusRejected {
		t.Errorf("Expected final status to be %s, got %s", domain.StatusRejected, result.FinalStatus)
	}
}

func TestOrderManager_Open_SlippageInvalid(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	// Create simulator that returns invalid slippage
	sim := &mockSimulator{
		simulateFunc: func(ctx context.Context, req simulation.SimulationRequest) (*simulation.SimulationResponse, error) {
			return &simulation.SimulationResponse{
				Result: &domain.SimulationResult{
					Success: true,
					OutputAmounts: []domain.TokenAmount{},
				},
				HoneypotDetected: false,
				SlippageValid:    false,
			}, nil
		},
	}

	om := execution.NewDefaultOrderManager(deps, config, sim)

	intent := execution.OpenIntent{
		PositionID: "pos-slippage",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}

	result := om.Open(ctx, intent)

	if result.Success {
		t.Error("Expected Open to fail when slippage is invalid")
	}
	if result.FinalStatus != domain.StatusRejected {
		t.Errorf("Expected final status to be %s, got %s", domain.StatusRejected, result.FinalStatus)
	}
}

func TestOrderManager_Open_MissingSimulation(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// Intent without simulation
	intent := execution.OpenIntent{
		PositionID: "pos-no-sim",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: nil,
	}

	result := om.Open(ctx, intent)

	if result.Success {
		t.Error("Expected Open to fail when simulation is missing")
	}
}

func TestOrderManager_Close_Success(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// First open a position
	openIntent := execution.OpenIntent{
		PositionID: "pos-close-test",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}
	om.Open(ctx, openIntent)

	// Now close the position
	closeIntent := execution.ExitIntent{
		PositionID: "pos-close-test",
		Chain:      "base",
		Reason:     "stop_loss",
		TraceID:    "trace-456",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}

	result := om.Close(ctx, closeIntent)

	if !result.Success {
		t.Errorf("Expected Close to succeed, got error: %s", result.Error)
	}
	if result.FinalStatus != domain.StatusClosed {
		t.Errorf("Expected final status to be %s, got %s", domain.StatusClosed, result.FinalStatus)
	}
}

func TestOrderManager_Close_PositionNotFound(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	closeIntent := execution.ExitIntent{
		PositionID: "non-existent-pos",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
		},
	}

	result := om.Close(ctx, closeIntent)

	if result.Success {
		t.Error("Expected Close to fail when position not found")
	}
}

func TestOrderManager_Rebalance_Success(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// First open a position
	openIntent := execution.OpenIntent{
		PositionID: "pos-rebalance-test",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}
	om.Open(ctx, openIntent)

	// Now rebalance the position
	rebalanceIntent := execution.RebalanceIntent{
		PositionID:   "pos-rebalance-test",
		Chain:        "base",
		NewTickLower: 150,
		NewTickUpper: 250,
		TraceID:      "trace-789",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
		},
	}

	result := om.Rebalance(ctx, rebalanceIntent)

	if !result.Success {
		t.Errorf("Expected Rebalance to succeed, got error: %s", result.Error)
	}
	if result.FinalStatus != domain.StatusOpen {
		t.Errorf("Expected final status to be %s after rebalance, got %s", domain.StatusOpen, result.FinalStatus)
	}
}

func TestOrderManager_Rebalance_PositionNotFound(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	rebalanceIntent := execution.RebalanceIntent{
		PositionID:   "non-existent-pos",
		Chain:        "base",
		NewTickLower: 150,
		NewTickUpper: 250,
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
		},
	}

	result := om.Rebalance(ctx, rebalanceIntent)

	if result.Success {
		t.Error("Expected Rebalance to fail when position not found")
	}
}

func TestOrderManager_CollectFees_Success(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// First open a position
	openIntent := execution.OpenIntent{
		PositionID: "pos-collect-test",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}
	om.Open(ctx, openIntent)

	// Now collect fees
	result := om.CollectFees(ctx, "pos-collect-test")

	if !result.Success {
		t.Errorf("Expected CollectFees to succeed, got error: %s", result.Error)
	}
	if result.PositionID != "pos-collect-test" {
		t.Errorf("Expected position ID to be pos-collect-test, got %s", result.PositionID)
	}
}

func TestOrderManager_CollectFees_PositionNotFound(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	result := om.CollectFees(ctx, "non-existent-pos")

	if result.Success {
		t.Error("Expected CollectFees to fail when position not found")
	}
}

func TestOrderManager_UpdateTxStatus(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// In shadow mode, UpdateTxStatus is a no-op and should not panic
	err := om.UpdateTxStatus(ctx, "some-tx-hash", domain.TxMined)

	if err != nil {
		t.Errorf("Expected UpdateTxStatus to return nil in shadow mode, got error: %v", err)
	}
}

func TestOrderManager_GetPendingTxs(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// In shadow mode, GetPendingTxs should return empty (no broadcast)
	txs, err := om.GetPendingTxs(ctx)

	if err != nil {
		t.Errorf("Expected GetPendingTxs to succeed, got error: %v", err)
	}
	if len(txs) != 0 {
		t.Errorf("Expected no pending transactions in shadow mode, got %d", len(txs))
	}
}

func TestOrderManager_RetryStuck(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	// In shadow mode, RetryStuck should return error (RBF not supported)
	result, err := om.RetryStuck(ctx, "some-tx-hash")

	if err != nil {
		t.Errorf("Expected RetryStuck to return nil error, got error: %v", err)
	}
	if result.Success {
		t.Error("Expected RetryStuck to fail in shadow mode")
	}
}

func TestOrderManager_Config(t *testing.T) {
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	sim := &mockSimulator{}
	om := execution.NewDefaultOrderManager(deps, config, sim)

	retrievedConfig := om.Config()

	if retrievedConfig.StuckTimeout != config.StuckTimeout {
		t.Errorf("Expected StuckTimeout to be %d, got %d", config.StuckTimeout, retrievedConfig.StuckTimeout)
	}
	if retrievedConfig.MaxRBFAttempts != config.MaxRBFAttempts {
		t.Errorf("Expected MaxRBFAttempts to be %d, got %d", config.MaxRBFAttempts, retrievedConfig.MaxRBFAttempts)
	}
}

func TestOrderManager_Close_SimulationReverted(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	// Create simulator that returns different results based on purpose
	sim := &mockSimulator{
		simulateFunc: func(ctx context.Context, req simulation.SimulationRequest) (*simulation.SimulationResponse, error) {
			// Open succeeds, close fails with revert
			if req.Purpose == "honeypot_check" {
				return &simulation.SimulationResponse{
					Result: &domain.SimulationResult{
						Success: true,
						OutputAmounts: []domain.TokenAmount{
							{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
						},
					},
					HoneypotDetected: false,
					SlippageValid:    true,
				}, nil
			}
			// Close fails with revert
			return &simulation.SimulationResponse{
				Result: &domain.SimulationResult{
					Success: false,
					Error:   "execution reverted: INSUFFICIENT_LIQUIDITY",
				},
				HoneypotDetected: false,
				SlippageValid:    true,
			}, nil
		},
	}

	om := execution.NewDefaultOrderManager(deps, config, sim)

	// Open first
	openIntent := execution.OpenIntent{
		PositionID: "pos-revert-test",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}
	om.Open(ctx, openIntent)

	// Try to close
	closeIntent := execution.ExitIntent{
		PositionID: "pos-revert-test",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
		},
	}

	result := om.Close(ctx, closeIntent)

	if result.Success {
		t.Error("Expected Close to fail when simulation reverts")
	}
	if result.FinalStatus != domain.StatusExitFailed {
		t.Errorf("Expected final status to be %s, got %s", domain.StatusExitFailed, result.FinalStatus)
	}
}

func TestOrderManager_Rebalance_SimulationFailed(t *testing.T) {
	ctx := context.Background()
	deps := execution.ExecutionDependencies{
		Chain:  &mockChain{info: ports.ChainInfo{ID: "base"}},
		Wallet: &mockWallet{address: domain.MustParseAddress("0x0000000000000000000000000000000000000001"), chain: "base"},
	}
	config := execution.DefaultExecutionConfig()

	// Create simulator that fails on sequence simulation
	sim := &mockSimulator{
		simulateSequenceFunc: func(ctx context.Context, reqs []simulation.SimulationRequest) ([]simulation.SimulationResponse, error) {
			return nil, ErrSimulationFailed
		},
	}

	om := execution.NewDefaultOrderManager(deps, config, sim)

	// Open first
	openIntent := execution.OpenIntent{
		PositionID: "pos-sim-fail-test",
		PoolID:     "pool-1",
		Chain:      "base",
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
			OutputAmounts: []domain.TokenAmount{
				{Token: domain.Token{Address: domain.MustParseAddress("0x0000000000000000000000000000000000000001")}, Amount: domain.MustDecimal("1")},
			},
		},
	}
	om.Open(ctx, openIntent)

	// Try to rebalance
	rebalanceIntent := execution.RebalanceIntent{
		PositionID:   "pos-sim-fail-test",
		Chain:        "base",
		NewTickLower: 150,
		NewTickUpper: 250,
		Simulation: &domain.SimulationResult{
			Success: true,
			BlockRef: domain.BlockRef{Chain: domain.ChainBase, Number: 1},
		},
	}

	result := om.Rebalance(ctx, rebalanceIntent)

	if result.Success {
		t.Error("Expected Rebalance to fail when simulation fails")
	}
}