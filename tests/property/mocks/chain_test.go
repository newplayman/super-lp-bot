package mocks

import (
	"testing"

	"github.com/lpbot/lpbot/internal/ports"
)

// compileTimeAssertions performs compile-time interface verification.
// These variables verify at compile time that MockChain, MockEVMChain,
// and MockSolanaChain implement their respective ports interfaces.
//
// If any mock doesn't implement its interface correctly, this file
// will fail to compile with an error like:
//   "cannot use (*MockXxx)(nil) as ports.Xxx value in variable declaration"

var (
	// Verify MockChain implements ports.Chain
	_ ports.Chain = (*MockChain)(nil)

	// Verify MockEVMChain implements ports.EVMChain
	_ ports.EVMChain = (*MockEVMChain)(nil)

	// Verify MockSolanaChain implements ports.SolanaChain
	_ ports.SolanaChain = (*MockSolanaChain)(nil)

	// Verify EVMChain implementations also implement Chain (interface embedding)
	_ ports.Chain = (*MockEVMChain)(nil)

	// Verify SolanaChain implementations also implement Chain (interface embedding)
	_ ports.Chain = (*MockSolanaChain)(nil)
)

// TestCompileTimeAssertions is a placeholder test to ensure this file runs.
// The real verification happens at compile time via the variable declarations above.
func TestCompileTimeAssertions(t *testing.T) {
	// If this test runs, all compile-time interface assertions passed.
	// This is a success condition - it means the mocks implement all required interfaces.
}