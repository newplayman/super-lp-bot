package simulation_test

import (
	"context"
	"errors"
	"testing"

	"github.com/lpbot/lpbot/internal/core/simulation"
	"github.com/lpbot/lpbot/internal/domain"
)

// Compile-time assertion: simulation.Simulator interface must be implemented.
var _ simulation.Simulator = (*simulationMock)(nil)

type simulationMock struct{}

func (m *simulationMock) SimulateAndValidate(ctx context.Context, req simulation.SimulationRequest) (*simulation.SimulationResponse, error) {
	return nil, nil
}

func (m *simulationMock) SimulateSequenceAndValidate(ctx context.Context, reqs []simulation.SimulationRequest) ([]simulation.SimulationResponse, error) {
	return nil, nil
}

// mockPortsSimulator implements ports.Simulator for testing
type mockPortsSimulator struct{}

func (m *mockPortsSimulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return nil, nil
}

func (m *mockPortsSimulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	return nil, nil
}

// TestSimulationInterfaceCompilation verifies that the Simulator interface
// can be satisfied by a concrete type at compile time.
func TestSimulationInterfaceCompilation(t *testing.T) {
	// Test that the interface can be assigned to a variable
	var _ simulation.Simulator = &simulationMock{}

	// Test that New returns a non-nil simulator when given a valid ports.Simulator
	sim := simulation.New(&mockPortsSimulator{}, simulation.DefaultSimulationConfig())
	if sim == nil {
		t.Fatal("simulation.New() returned nil")
	}
}

// TestSimulationRequestConstruction verifies SimulationRequest type construction.
func TestSimulationRequestConstruction(t *testing.T) {
	req := simulation.SimulationRequest{
		Purpose: "honeypot_check",
		TraceID: "test-trace-123",
		Tx:      domain.UnsignedTx{},
		BlockRef: domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 12345678,
		},
	}

	if req.Purpose != "honeypot_check" {
		t.Errorf("Expected Purpose='honeypot_check', got %q", req.Purpose)
	}
	if req.TraceID != "test-trace-123" {
		t.Errorf("Expected TraceID='test-trace-123', got %q", req.TraceID)
	}
}

// TestSimulationResponseConstruction verifies SimulationResponse type construction.
func TestSimulationResponseConstruction(t *testing.T) {
	resp := simulation.SimulationResponse{
		HoneypotDetected: false,
		SlippageValid:    true,
		GasEstimate:      domain.MustDecimal("0.001"),
	}

	if resp.HoneypotDetected != false {
		t.Errorf("Expected HoneypotDetected=false, got %v", resp.HoneypotDetected)
	}
	if resp.SlippageValid != true {
		t.Errorf("Expected SlippageValid=true, got %v", resp.SlippageValid)
	}
}

// TestDefaultSimulationConfig verifies the default configuration values.
func TestDefaultSimulationConfig(t *testing.T) {
	cfg := simulation.DefaultSimulationConfig()

	if cfg.MaxSlippageBps != 50 {
		t.Errorf("Expected MaxSlippageBps=50, got %d", cfg.MaxSlippageBps)
	}
	if cfg.HoneypotThreshold != 0.1 {
		t.Errorf("Expected HoneypotThreshold=0.1, got %f", cfg.HoneypotThreshold)
	}
	if !cfg.GasEstimateBuffer.Equal(domain.MustDecimal("1200000")) {
		t.Errorf("Expected GasEstimateBuffer=1200000, got %s", cfg.GasEstimateBuffer.String())
	}
}

// testSimulator implements ports.Simulator for testing SimulateAndValidate
type testSimulator struct {
	simulateFunc func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error)
}

func (m *testSimulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	if m.simulateFunc != nil {
		return m.simulateFunc(ctx, tx, blockRef)
	}
	return nil, nil
}

func (m *testSimulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	return nil, nil
}

// TestSimulateAndValidate_Success tests the happy path for SimulateAndValidate.
func TestSimulateAndValidate_Success(t *testing.T) {
	mockSim := &testSimulator{
		simulateFunc: func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
			return &domain.SimulationResult{
				Success:  true,
				GasUsed:  200_000,
				OutputAmounts: []domain.TokenAmount{
					{Amount: domain.MustDecimal("1000")},
				},
			}, nil
		},
	}

	cfg := simulation.DefaultSimulationConfig()
	sim := simulation.New(mockSim, cfg)

	req := simulation.SimulationRequest{
		Tx: domain.UnsignedTx{
			MinOut: domain.MustDecimal("900"),
		},
		BlockRef: domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 12345678,
		},
	}

	resp, err := sim.SimulateAndValidate(context.Background(), req)
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}
	if resp == nil {
		t.Fatal("Expected response, got nil")
	}
	if !resp.Result.Success {
		t.Errorf("Expected Result.Success=true, got %v", resp.Result.Success)
	}
	if resp.HoneypotDetected {
		t.Errorf("Expected HoneypotDetected=false, got %v", resp.HoneypotDetected)
	}
	if !resp.SlippageValid {
		t.Errorf("Expected SlippageValid=true, got %v", resp.SlippageValid)
	}
}

// TestSimulateAndValidate_HoneypotDetection tests honeypot detection when gas is abnormal.
func TestSimulateAndValidate_HoneypotDetection(t *testing.T) {
	// Gas used is 3x expected (ratio = 2.0, which is > 0.1 threshold)
	mockSim := &testSimulator{
		simulateFunc: func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
			return &domain.SimulationResult{
				Success:  true,
				GasUsed:  600_000, // Very high gas usage - suggests honeypot
				OutputAmounts: []domain.TokenAmount{
					{Amount: domain.MustDecimal("1000")},
				},
			}, nil
		},
	}

	cfg := simulation.DefaultSimulationConfig()
	sim := simulation.New(mockSim, cfg)

	req := simulation.SimulationRequest{
		Tx: domain.UnsignedTx{
			MinOut: domain.MustDecimal("900"),
		},
		BlockRef: domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 12345678,
		},
	}

	resp, err := sim.SimulateAndValidate(context.Background(), req)
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}
	if resp == nil {
		t.Fatal("Expected response, got nil")
	}
	if !resp.HoneypotDetected {
		t.Errorf("Expected HoneypotDetected=true for high gas usage, got %v", resp.HoneypotDetected)
	}
}

// TestSimulateAndValidate_SlippageValidation tests slippage validation when over limit.
func TestSimulateAndValidate_SlippageValidation(t *testing.T) {
	mockSim := &testSimulator{
		simulateFunc: func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
			return &domain.SimulationResult{
				Success: true,
				GasUsed: 200_000,
				OutputAmounts: []domain.TokenAmount{
					{Amount: domain.MustDecimal("100")}, // Very low output
				},
			}, nil
		},
	}

	cfg := simulation.DefaultSimulationConfig()
	sim := simulation.New(mockSim, cfg)

	// MinOut is 900, output is 100 - slippage is 800/900 = 88.8%, way over 0.5% limit
	req := simulation.SimulationRequest{
		Tx: domain.UnsignedTx{
			MinOut: domain.MustDecimal("900"),
		},
		BlockRef: domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 12345678,
		},
	}

	resp, err := sim.SimulateAndValidate(context.Background(), req)
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}
	if resp == nil {
		t.Fatal("Expected response, got nil")
	}
	if resp.SlippageValid {
		t.Errorf("Expected SlippageValid=false for high slippage, got %v", resp.SlippageValid)
	}
}

// TestSimulateAndValidate_ErrorPropagation tests that errors from the simulator are propagated.
func TestSimulateAndValidate_ErrorPropagation(t *testing.T) {
	expectedErr := errors.New("RPC error: connection refused")
	mockSim := &testSimulator{
		simulateFunc: func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
			return nil, expectedErr
		},
	}

	cfg := simulation.DefaultSimulationConfig()
	sim := simulation.New(mockSim, cfg)

	req := simulation.SimulationRequest{
		Tx: domain.UnsignedTx{},
		BlockRef: domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 12345678,
		},
	}

	resp, err := sim.SimulateAndValidate(context.Background(), req)
	if err == nil {
		t.Fatal("Expected error, got nil")
	}
	if resp != nil {
		t.Errorf("Expected nil response on error, got %+v", resp)
	}
}

// TestDetectHoneypot_NilResult tests that nil result returns false.
func TestDetectHoneypot_NilResult(t *testing.T) {
	mockSim := &testSimulator{
		simulateFunc: func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
			return nil, nil
		},
	}

	cfg := simulation.DefaultSimulationConfig()
	sim := simulation.New(mockSim, cfg)

	req := simulation.SimulationRequest{
		Tx: domain.UnsignedTx{},
		BlockRef: domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 12345678,
		},
	}

	resp, err := sim.SimulateAndValidate(context.Background(), req)
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}
	// With nil result, we still get a response but with nil Result
	if resp.HoneypotDetected {
		t.Errorf("Expected HoneypotDetected=false for nil result, got %v", resp.HoneypotDetected)
	}
}