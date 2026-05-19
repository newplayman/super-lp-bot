// Package postgres provides a PostgreSQL-backed implementation of storage adapters.
// Actual implementation deferred to Phase 3.
//
// Interfaces implemented:
//   - ports.TxRepo (internal/ports/store_tx.go)
//   - ports.PositionRepo (internal/ports/store_position.go)
//   - ports.PoolRepo (internal/ports/store_pool.go)
//   - ports.ConfigSnap (internal/ports/store_config.go)
//   - ports.RiskRepo (internal/ports/store_risk.go)
//   - ports.ReconRepo (internal/ports/store_recon.go)
//   - ports.LedgerRepo (internal/ports/store_ledger.go)
package postgres