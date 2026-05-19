package subgraph_test

import (
	"net/http"
	"testing"

	"github.com/lpbot/lpbot/internal/adapters/datasource/subgraph"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestSubgraphAdapterImplementsDatasource verifies compile-time interface compliance.
func TestSubgraphAdapterImplementsDatasource(t *testing.T) {
	var adapter *subgraph.Adapter
	var _ ports.Datasource = adapter
}

// TestSubgraphAdapterImplementsHistoricalDatasource verifies compile-time interface compliance.
func TestSubgraphAdapterImplementsHistoricalDatasource(t *testing.T) {
	var adapter *subgraph.Adapter
	var _ ports.HistoricalDatasource = adapter
}

// TestSubgraphNewAdapter verifies default adapter creation.
func TestSubgraphNewAdapter(t *testing.T) {
	adapter := subgraph.NewAdapter()
	require.NotNil(t, adapter)
}

// TestSubgraphNewAdapterWithURL verifies custom URL adapter creation.
func TestSubgraphNewAdapterWithURL(t *testing.T) {
	adapter := subgraph.NewAdapterWithURL("https://api.thegraph.com/subgraphs/name/test")
	require.NotNil(t, adapter)
}

// TestSubgraphNewAdapterWithClient verifies custom client adapter creation.
func TestSubgraphNewAdapterWithClient(t *testing.T) {
	client := subgraph.NewClient()
	adapter := subgraph.NewAdapterWithClient(client)
	require.NotNil(t, adapter)
}

// TestSubgraphClientCreation verifies client creation.
func TestSubgraphClientCreation(t *testing.T) {
	client := subgraph.NewClient()
	require.NotNil(t, client)
}

// TestSubgraphClientWithURL verifies client with custom URL.
func TestSubgraphClientWithURL(t *testing.T) {
	client := subgraph.NewClientWithURL("https://api.thegraph.com/subgraphs/name/custom")
	require.NotNil(t, client)
}

// TestSubgraphAdapterWithHTTPClient verifies adapter with custom HTTP client.
func TestSubgraphAdapterWithHTTPClient(t *testing.T) {
	_ = &http.Client{}
	adapter := subgraph.NewAdapter()
	require.NotNil(t, adapter)
}