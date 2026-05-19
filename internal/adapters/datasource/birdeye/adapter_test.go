package birdeye_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/adapters/datasource/birdeye"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestBirdeyeAdapterInterface verifies the adapter implements ports.Datasource.
func TestBirdeyeAdapterInterface(t *testing.T) {
	adapter := birdeye.NewBirdeyeAdapter()
	var _ ports.Datasource = adapter
}

// TestBirdeyeDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestBirdeyeDiscoverPoolsStub(t *testing.T) {
	adapter := birdeye.NewBirdeyeAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, birdeye.ErrNotImplemented, err)
}

// TestBirdeyeGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestBirdeyeGetPoolMetadataStub(t *testing.T) {
	adapter := birdeye.NewBirdeyeAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainBase, "0x123")
	require.Error(t, err)
	require.Equal(t, birdeye.ErrNotImplemented, err)
}

// TestBirdeyeHealthCheckStub verifies HealthCheck returns not implemented.
func TestBirdeyeHealthCheckStub(t *testing.T) {
	adapter := birdeye.NewBirdeyeAdapter()
	err := adapter.HealthCheck(context.Background())
	require.Error(t, err)
	require.Equal(t, birdeye.ErrNotImplemented, err)
}