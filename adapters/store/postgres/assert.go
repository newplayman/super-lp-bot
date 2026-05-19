// Package postgres provides PostgreSQL adapter stubs for storage ports.
// This file documents which ports the postgres adapter implements.
// Actual implementation deferred to Phase 3.

package postgres

import (
	"github.com/lpbot/lpbot/internal/ports"
)

var (
	_ ports.TxRepo       = (*TxRepoStub)(nil)
	_ ports.PositionRepo = (*PositionRepoStub)(nil)
	_ ports.PoolRepo     = (*PoolRepoStub)(nil)
	_ ports.ConfigSnap   = (*ConfigSnapStub)(nil)
	_ ports.RiskRepo     = (*RiskRepoStub)(nil)
	_ ports.ReconRepo    = (*ReconRepoStub)(nil)
	_ ports.LedgerRepo   = (*LedgerRepoStub)(nil)
)

type (
	TxRepoStub       struct{}
	PositionRepoStub struct{}
	PoolRepoStub     struct{}
	ConfigSnapStub   struct{}
	RiskRepoStub     struct{}
	ReconRepoStub    struct{}
	LedgerRepoStub   struct{}
)