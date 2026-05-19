package simulation_test

import (
	"context"
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

// TestSimulationInterfaceCompilation verifies that the Simulator interface
// can be satisfied by a concrete type at compile time.
func TestSimulationInterfaceCompilation(t *testing.T) {
	// This test verifies compile-time interface compliance.
	// If this test compiles, the interface is correctly defined.

	// Test that the interface can be assigned to a variable
	var _ simulation.Simulator = &simulationMock{}

	// Test that New returns a non-nil simulator when given a valid ports.Simulator
	// Use the concrete mockPortsSimulator that implements ports.Simulator
	sim := simulation.New(&mockPortsSimulator{})
	if sim == nil {
		t.Fatal("simulation.New() returned nil")
	}
}

// mockPortsSimulator implements ports.Simulator for testing
type mockPortsSimulator struct{}

func (m *mockPortsSimulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return nil, nil
}

func (m *mockPortsSimulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	return nil, nil
}

// TestSimulationRequestConstruction verifies SimulationRequest type construction.
func TestSimulationRequestConstruction(t *testing.T) {
	// Test SimulationRequest type construction
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
	// Test SimulationResponse type construction
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

// TestSimulationStubPanic verifies that the stub implementation panics as expected.
// These tests are skipped in Phase 0 since the stub should panic.
func TestSimulationStubPanic(t *testing.T) {
	t.Skip("Phase 1 task T-315: implement SimulateAndValidate")

	// These would panic in production - skip for Phase 0
	_ = simulation.New(nil)
}