package defillama_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/adapters/datasource/defillama"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestDeFiLlamaAdapterInterface verifies the adapter implements ports.Datasource.
func TestDeFiLlamaAdapterInterface(t *testing.T) {
	adapter := defillama.NewDeFiLlamaAdapter()
	var _ ports.Datasource = adapter
}

// TestDeFiLlamaDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestDeFiLlamaDiscoverPoolsStub(t *testing.T) {
	adapter := defillama.NewDeFiLlamaAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, defillama.ErrNotImplemented, err)
}

// TestDeFiLlamaGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestDeFiLlamaGetPoolMetadataStub(t *testing.T) {
	adapter := defillama.NewDeFiLlamaAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainBase, "0x123")
	require.Error(t, err)
	require.Equal(t, defillama.ErrNotImplemented, err)
}

// TestDeFiLlamaHealthCheckStub verifies HealthCheck returns not implemented.
func TestDeFiLlamaHealthCheckStub(t *testing.T) {
	adapter := defillama.NewDeFiLlamaAdapter()
	err := adapter.HealthCheck(context.Background())
	require.Error(t, err)
	require.Equal(t, defillama.ErrNotImplemented, err)
}