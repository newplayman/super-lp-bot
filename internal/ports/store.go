// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// The Store interface provides unified access to all repository interfaces.
package ports

// Store provides unified access to all repository interfaces.
// Implementations aggregate multiple repositories under a single interface.
//
// Store is designed for components that need access to multiple repositories
// without depending on specific storage implementations.
//
// Implementations must be safe for concurrent use.
type Store interface {
	// TxRepo returns the transaction repository.
	TxRepo() TxRepo

	// PositionRepo returns the position repository.
	PositionRepo() PositionRepo

	// PoolRepo returns the pool repository.
	PoolRepo() PoolRepo

	// LedgerRepo returns the ledger repository.
	LedgerRepo() LedgerRepo

	// RiskRepo returns the risk repository.
	RiskRepo() RiskRepo

	// ConfigSnap returns the config snapshot repository.
	ConfigSnap() ConfigSnap
}