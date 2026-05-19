// Package defillama provides a DeFi Llama datasource adapter.
//
// This adapter fetches pool discovery and metadata from DeFi Llama API.
// Phase 1 implementation.
package defillama

import (
	"context"
	"errors"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Compile-time interface assertion: DeFiLlamaAdapter implements ports.Datasource
var _ ports.Datasource = (*DeFiLlamaAdapter)(nil)

// ErrNotImplemented is returned for operations not yet implemented.
var ErrNotImplemented = errors.New("not implemented: DeFiLlama Phase 1")

// DeFiLlamaAdapter implements ports.Datasource for DeFi Llama.
type DeFiLlamaAdapter struct{}

// NewDeFiLlamaAdapter creates a new DeFi Llama adapter.
func NewDeFiLlamaAdapter() *DeFiLlamaAdapter {
	return &DeFiLlamaAdapter{}
}

// DiscoverPools returns pools from DeFi Llama API.
// Phase 1 stub: returns ErrNotImplemented.
func (a *DeFiLlamaAdapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// GetPoolMetadata returns pool metadata from DeFi Llama API.
// Phase 1 stub: returns ErrNotImplemented.
func (a *DeFiLlamaAdapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// HealthCheck verifies DeFi Llama API connectivity.
// Phase 1 stub: returns ErrNotImplemented.
func (a *DeFiLlamaAdapter) HealthCheck(ctx context.Context) error {
	return ErrNotImplemented
}