package mocks

import (
	"context"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// MockDatasource implements ports.Datasource and ports.HistoricalDatasource for testing.
type MockDatasource struct {
	Pools           []ports.PoolDiscovery
	HistoricalPrices [][]ports.HistoricalPrice
	Swaps           [][]ports.Swap

	DiscoverPoolsHook      func(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error)
	GetPoolMetadataHook     func(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error)
	HealthCheckHook         func(ctx context.Context) error
	GetPriceHistoryHook     func(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error)
	GetSwapsHook            func(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error)
	GetPoolStateAtHook      func(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error)
}

func NewMockDatasource() *MockDatasource {
	return &MockDatasource{}
}

func (m *MockDatasource) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	if m.DiscoverPoolsHook != nil {
		return m.DiscoverPoolsHook(ctx, chain, protocol, minTVLUSD, limit)
	}
	return m.Pools, nil
}

func (m *MockDatasource) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	if m.GetPoolMetadataHook != nil {
		return m.GetPoolMetadataHook(ctx, chain, poolID)
	}
	for i := range m.Pools {
		if m.Pools[i].ID == poolID && m.Pools[i].Chain == chain {
			return &m.Pools[i], nil
		}
	}
	return nil, nil
}

func (m *MockDatasource) HealthCheck(ctx context.Context) error {
	if m.HealthCheckHook != nil {
		return m.HealthCheckHook(ctx)
	}
	return nil
}

func (m *MockDatasource) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	if m.GetPriceHistoryHook != nil {
		return m.GetPriceHistoryHook(ctx, chain, poolID, from, to, resolution)
	}
	if len(m.HistoricalPrices) > 0 {
		return m.HistoricalPrices[0], nil
	}
	return nil, nil
}

func (m *MockDatasource) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	if m.GetSwapsHook != nil {
		return m.GetSwapsHook(ctx, chain, poolID, from, to, limit)
	}
	if len(m.Swaps) > 0 {
		return m.Swaps[0], nil
	}
	return nil, nil
}

func (m *MockDatasource) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	if m.GetPoolStateAtHook != nil {
		return m.GetPoolStateAtHook(ctx, chain, poolID, blockNumber)
	}
	return m.GetPoolMetadata(ctx, chain, poolID)
}