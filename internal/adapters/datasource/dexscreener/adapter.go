// Package dexscreener provides a DexScreener datasource adapter.
//
// This adapter fetches pool discovery and metadata from DexScreener API.
// Actual implementation in milestone 0.11.
//
// Phase: M0.11 (stub only in M0.1)
package dexscreener

import (
	"context"
	"errors"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Compile-time interface assertion: DexScreenerAdapter implements ports.Datasource
var _ ports.Datasource = (*DexScreenerAdapter)(nil)

// ErrNotImplemented is returned for operations not yet implemented.
var ErrNotImplemented = errors.New("not implemented: DexScreener M0.11")

// DexScreenerAdapter implements ports.Datasource for DexScreener.
// This is a Phase 1 stub; actual implementation in milestone 0.11.
type DexScreenerAdapter struct{}

// NewDexScreenerAdapter creates a new DexScreener adapter (stub).
func NewDexScreenerAdapter() *DexScreenerAdapter {
	return &DexScreenerAdapter{}
}

// DiscoverPools returns pools from DexScreener.
// Stub: returns ErrNotImplemented.
func (a *DexScreenerAdapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// GetPoolMetadata returns pool metadata from DexScreener.
// Stub: returns ErrNotImplemented.
func (a *DexScreenerAdapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// HealthCheck verifies DexScreener API connectivity.
// Stub: returns ErrNotImplemented.
func (a *DexScreenerAdapter) HealthCheck(ctx context.Context) error {
	return ErrNotImplemented
}