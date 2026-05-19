// Package birdeye provides a Birdeye datasource adapter.
//
// This adapter fetches pool discovery and metadata from Birdeye API.
// Phase 1 implementation.
package birdeye

import (
	"context"
	"errors"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Compile-time interface assertion: BirdeyeAdapter implements ports.Datasource
var _ ports.Datasource = (*BirdeyeAdapter)(nil)

// ErrNotImplemented is returned for operations not yet implemented.
var ErrNotImplemented = errors.New("not implemented: Birdeye Phase 1")

// BirdeyeAdapter implements ports.Datasource for Birdeye.
type BirdeyeAdapter struct{}

// NewBirdeyeAdapter creates a new Birdeye adapter.
func NewBirdeyeAdapter() *BirdeyeAdapter {
	return &BirdeyeAdapter{}
}

// DiscoverPools returns pools from Birdeye API.
// Phase 1 stub: returns ErrNotImplemented.
func (a *BirdeyeAdapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// GetPoolMetadata returns pool metadata from Birdeye API.
// Phase 1 stub: returns ErrNotImplemented.
func (a *BirdeyeAdapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// HealthCheck verifies Birdeye API connectivity.
// Phase 1 stub: returns ErrNotImplemented.
func (a *BirdeyeAdapter) HealthCheck(ctx context.Context) error {
	return ErrNotImplemented
}