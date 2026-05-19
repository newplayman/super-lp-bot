// Package geckoterminal provides a GeckoTerminal datasource adapter.
//
// This adapter fetches pool discovery and metadata from GeckoTerminal API.
// Phase 1 implementation.
package geckoterminal

import (
	"context"
	"errors"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Compile-time interface assertion: GeckoTerminalAdapter implements ports.Datasource
var _ ports.Datasource = (*GeckoTerminalAdapter)(nil)

// ErrNotImplemented is returned for operations not yet implemented.
var ErrNotImplemented = errors.New("not implemented: GeckoTerminal Phase 1")

// GeckoTerminalAdapter implements ports.Datasource for GeckoTerminal.
type GeckoTerminalAdapter struct{}

// NewGeckoTerminalAdapter creates a new GeckoTerminal adapter.
func NewGeckoTerminalAdapter() *GeckoTerminalAdapter {
	return &GeckoTerminalAdapter{}
}

// DiscoverPools returns pools from GeckoTerminal API.
// Phase 1 stub: returns ErrNotImplemented.
func (a *GeckoTerminalAdapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// GetPoolMetadata returns pool metadata from GeckoTerminal API.
// Phase 1 stub: returns ErrNotImplemented.
func (a *GeckoTerminalAdapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

// HealthCheck verifies GeckoTerminal API connectivity.
// Phase 1 stub: returns ErrNotImplemented.
func (a *GeckoTerminalAdapter) HealthCheck(ctx context.Context) error {
	return ErrNotImplemented
}