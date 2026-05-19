package subgraph_test

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/subgraph"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestSubgraphAdapterInterface verifies the adapter implements ports.Datasource.
func TestSubgraphAdapterInterface(t *testing.T) {
	adapter := subgraph.NewAdapter()
	var _ ports.Datasource = adapter
}

// TestSubgraphAdapterHistoricalInterface verifies the adapter implements ports.HistoricalDatasource.
func TestSubgraphAdapterHistoricalInterface(t *testing.T) {
	adapter := subgraph.NewAdapter()
	var _ ports.HistoricalDatasource = adapter
}

// TestSubgraphDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestSubgraphDiscoverPoolsStub(t *testing.T) {
	adapter := subgraph.NewAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, subgraph.ErrNotImplemented, err)
}

// TestSubgraphGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestSubgraphGetPoolMetadataStub(t *testing.T) {
	adapter := subgraph.NewAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainBase, "0x123")
	require.Error(t, err)
	require.Equal(t, subgraph.ErrNotImplemented, err)
}

// TestSubgraphGetPriceHistoryStub verifies GetPriceHistory returns not implemented.
func TestSubgraphGetPriceHistoryStub(t *testing.T) {
	adapter := subgraph.NewAdapter()
	_, err := adapter.GetPriceHistory(context.Background(), domain.ChainBase, "0x123", time.Time{}, time.Now(), time.Hour)
	require.Error(t, err)
	require.Equal(t, subgraph.ErrNotImplemented, err)
}

// TestSubgraphGetPoolStateAtStub verifies GetPoolStateAt returns not implemented.
func TestSubgraphGetPoolStateAtStub(t *testing.T) {
	adapter := subgraph.NewAdapter()
	_, err := adapter.GetPoolStateAt(context.Background(), domain.ChainBase, "0x123", 1000)
	require.Error(t, err)
	require.Equal(t, subgraph.ErrNotImplemented, err)
}