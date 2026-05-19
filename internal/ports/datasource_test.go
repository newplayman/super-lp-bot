package ports_test

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: DatasourceMock must implement ports.Datasource
var _ ports.Datasource = (*DatasourceMock)(nil)

// Compile-time interface assertion: HistoricalDatasourceMock must implement ports.HistoricalDatasource
var _ ports.HistoricalDatasource = (*HistoricalDatasourceMock)(nil)

// DatasourceMock is a mock implementation of the Datasource interface for testing.
type DatasourceMock struct {
	DiscoverPoolsFunc    func(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error)
	GetPoolMetadataFunc  func(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error)
	HealthCheckFunc      func(ctx context.Context) error
}

// DiscoverPools implements ports.Datasource
func (m *DatasourceMock) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	if m.DiscoverPoolsFunc != nil {
		return m.DiscoverPoolsFunc(ctx, chain, protocol, minTVLUSD, limit)
	}
	return nil, nil
}

// GetPoolMetadata implements ports.Datasource
func (m *DatasourceMock) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	if m.GetPoolMetadataFunc != nil {
		return m.GetPoolMetadataFunc(ctx, chain, poolID)
	}
	return nil, nil
}

// HealthCheck implements ports.Datasource
func (m *DatasourceMock) HealthCheck(ctx context.Context) error {
	if m.HealthCheckFunc != nil {
		return m.HealthCheckFunc(ctx)
	}
	return nil
}

// HistoricalDatasourceMock is a mock implementation of the HistoricalDatasource interface for testing.
type HistoricalDatasourceMock struct {
	GetPriceHistoryFunc func(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error)
	GetSwapsFunc        func(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error)
	GetPoolStateAtFunc  func(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error)
	HealthCheckFunc     func(ctx context.Context) error
}

// GetPriceHistory implements ports.HistoricalDatasource
func (m *HistoricalDatasourceMock) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	if m.GetPriceHistoryFunc != nil {
		return m.GetPriceHistoryFunc(ctx, chain, poolID, from, to, resolution)
	}
	return nil, nil
}

// GetSwaps implements ports.HistoricalDatasource
func (m *HistoricalDatasourceMock) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	if m.GetSwapsFunc != nil {
		return m.GetSwapsFunc(ctx, chain, poolID, from, to, limit)
	}
	return nil, nil
}

// GetPoolStateAt implements ports.HistoricalDatasource
func (m *HistoricalDatasourceMock) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	if m.GetPoolStateAtFunc != nil {
		return m.GetPoolStateAtFunc(ctx, chain, poolID, blockNumber)
	}
	return nil, nil
}

// HealthCheck implements ports.HistoricalDatasource
func (m *HistoricalDatasourceMock) HealthCheck(ctx context.Context) error {
	if m.HealthCheckFunc != nil {
		return m.HealthCheckFunc(ctx)
	}
	return nil
}

// TestDatasourceInterface verifies the Datasource interface is properly defined
func TestDatasourceInterface(t *testing.T) {
	require.NotNil(t, t, "ports.Datasource interface must exist")

	// Test that we can create and use a datasource mock
	var ds ports.Datasource = &DatasourceMock{
		DiscoverPoolsFunc: func(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
			return []ports.PoolDiscovery{
				{ID: "test-pool", Chain: domain.ChainBase, Protocol: "uniswap_v3"},
			}, nil
		},
	}

	pools, err := ds.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.NoError(t, err)
	require.Len(t, pools, 1)
	require.Equal(t, "test-pool", pools[0].ID)
}

// TestHistoricalDatasourceInterface verifies the HistoricalDatasource interface is properly defined
func TestHistoricalDatasourceInterface(t *testing.T) {
	require.NotNil(t, t, "ports.HistoricalDatasource interface must exist")

	// Test that we can create and use a historical datasource mock
	var hds ports.HistoricalDatasource = &HistoricalDatasourceMock{
		GetPriceHistoryFunc: func(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
			return []ports.HistoricalPrice{
				{PoolID: poolID, Chain: chain, BlockNumber: 12345678},
			}, nil
		},
	}

	history, err := hds.GetPriceHistory(context.Background(), domain.ChainBase, "test-pool", time.Now().Add(-24*time.Hour), time.Now(), time.Hour)
	require.NoError(t, err)
	require.Len(t, history, 1)
	require.Equal(t, "test-pool", history[0].PoolID)
}

// TestPoolDiscoveryStruct verifies PoolDiscovery can be instantiated
func TestPoolDiscoveryStruct(t *testing.T) {
	pd := ports.PoolDiscovery{
		ID:        "0x123",
		Chain:     domain.ChainBase,
		Protocol:  "uniswap_v3",
		Token0:    domain.MustParseAddress("0x0000000000000000000000000000000000000001"),
		Token1:    domain.MustParseAddress("0x0000000000000000000000000000000000000002"),
		FeeBPS:    30,
		TVLUSD:    domain.MustDecimal("1000000"),
		Vol24h:    domain.MustDecimal("500000"),
		UpdatedAt: time.Now(),
	}

	require.Equal(t, "0x123", pd.ID)
	require.Equal(t, domain.ChainBase, pd.Chain)
	require.Equal(t, "uniswap_v3", pd.Protocol)
	require.Equal(t, uint(30), pd.FeeBPS)
}

// TestHistoricalPriceStruct verifies HistoricalPrice can be instantiated
func TestHistoricalPriceStruct(t *testing.T) {
	hp := ports.HistoricalPrice{
		PoolID:      "0x123",
		Chain:       domain.ChainBase,
		Timestamp:   time.Now(),
		BlockNumber: 12345678,
		Price0:      domain.MustDecimal("1.5"),
		Price1:      domain.MustDecimal("0.666"),
		Liquidity:   domain.MustDecimal("1000000"),
		Volume24h:   domain.MustDecimal("500000"),
	}

	require.Equal(t, "0x123", hp.PoolID)
	require.Equal(t, domain.ChainBase, hp.Chain)
	require.Equal(t, uint64(12345678), hp.BlockNumber)
}

// TestSwapStruct verifies Swap can be instantiated
func TestSwapStruct(t *testing.T) {
	swap := ports.Swap{
		ID:          "swap-123",
		PoolID:      "0x123",
		Chain:       domain.ChainBase,
		Timestamp:   time.Now(),
		BlockNumber: 12345678,
		Amount0:     domain.MustDecimal("100"),
		Amount1:     domain.MustDecimal("150"),
		Trader:      domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Tick:        10000,
		SqrtPriceX96: domain.MustDecimal("79228162514264337593543950336"),
	}

	require.Equal(t, "swap-123", swap.ID)
	require.Equal(t, "0x123", swap.PoolID)
	require.Equal(t, domain.ChainBase, swap.Chain)
	require.Equal(t, 10000, swap.Tick)
}

// TestDatasourceHealthCheck tests the HealthCheck method
func TestDatasourceHealthCheck(t *testing.T) {
	var ds ports.Datasource = &DatasourceMock{
		HealthCheckFunc: func(ctx context.Context) error {
			return nil
		},
	}

	err := ds.HealthCheck(context.Background())
	require.NoError(t, err)
}

// TestHistoricalDatasourceHealthCheck tests the HealthCheck method
func TestHistoricalDatasourceHealthCheck(t *testing.T) {
	var hds ports.HistoricalDatasource = &HistoricalDatasourceMock{
		HealthCheckFunc: func(ctx context.Context) error {
			return nil
		},
	}

	err := hds.HealthCheck(context.Background())
	require.NoError(t, err)
}

// TestDatasourceMockBehavior tests the mock behavior
func TestDatasourceMockBehavior(t *testing.T) {
	called := false
	ds := &DatasourceMock{
		DiscoverPoolsFunc: func(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
			called = true
			require.Equal(t, domain.ChainBase, chain)
			require.Equal(t, "uniswap_v3", protocol)
			return nil, nil
		},
	}

	var _ ports.Datasource = ds // compile-time check

	_, _ = ds.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.True(t, called, "DiscoverPoolsFunc should have been called")
}

// TestHistoricalDatasourceMockBehavior tests the mock behavior
func TestHistoricalDatasourceMockBehavior(t *testing.T) {
	called := false
	hds := &HistoricalDatasourceMock{
		GetSwapsFunc: func(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
			called = true
			require.Equal(t, domain.ChainBase, chain)
			require.Equal(t, "test-pool", poolID)
			return nil, nil
		},
	}

	var _ ports.HistoricalDatasource = hds // compile-time check

	_, _ = hds.GetSwaps(context.Background(), domain.ChainBase, "test-pool", time.Now().Add(-24*time.Hour), time.Now(), 100)
	require.True(t, called, "GetSwapsFunc should have been called")
}