package ports

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

// Compile-time assertion: Simulator interface must be implemented.
var _ Simulator = (*simulatorNop)(nil)

// simulatorNop is a no-op implementation for compile-time interface checks.
type simulatorNop struct{}

func (simulatorNop) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return nil, nil
}

func (simulatorNop) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	return nil, nil
}

// TestSimulatorInterfaceCompilation verifies that the Simulator interface
// can be satisfied by a concrete type at compile time.
func TestSimulatorInterfaceCompilation(t *testing.T) {
	// This test verifies compile-time interface compliance.
	// If this test compiles, the interface is correctly defined.

	// Test that the interface can be assigned to a variable
	var _ Simulator = &simulatorNop{}

	// Test anonymous implementation via function type
	var _ Simulator = SimulatorFunc(func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
		return nil, nil
	})

	// Verify the interface is not nil
	var sim Simulator = &simulatorNop{}
	if sim == nil {
		t.Error("Simulator interface should not be nil")
	}
}

// SimulatorFunc is a function-based implementation of Simulator for testing/mocking.
type SimulatorFunc func(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error)

// Simulate delegates to the underlying function.
func (f SimulatorFunc) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return f(ctx, tx, blockRef)
}

// SimulateSequence simulates multiple transactions sequentially.
func (f SimulatorFunc) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	var results []domain.SimulationResult
	for _, tx := range txs {
		result, err := f.Simulate(ctx, tx, blockRef)
		if err != nil {
			return results, err
		}
		results = append(results, *result)
	}
	return results, nil
}

// TestSimulatorFuncImplementation verifies that SimulatorFunc implements the Simulator interface.
func TestSimulatorFuncImplementation(t *testing.T) {
	// Compile-time check: SimulatorFunc must implement Simulator
	var _ Simulator = SimulatorFunc(nil)
}