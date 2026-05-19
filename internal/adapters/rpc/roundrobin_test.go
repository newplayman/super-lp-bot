// Package rpc provides tests for round-robin RPC provider.
package rpc

import (
	"testing"
)

func TestNewBaseProvider(t *testing.T) {
	// Test creating a provider with Base endpoints
	provider, err := NewBaseProvider()
	if err != nil {
		t.Fatalf("NewBaseProvider() failed: %v", err)
	}

	if provider == nil {
		t.Fatal("NewBaseProvider() returned nil provider")
	}

	if provider.chainID != "base" {
		t.Errorf("expected chainID 'base', got '%s'", provider.chainID)
	}

	if len(provider.endpoints) != 2 {
		t.Errorf("expected 2 endpoints, got %d", len(provider.endpoints))
	}

	// Check first endpoint
	if provider.endpoints[0] != "https://mainnet.base.org" {
		t.Errorf("expected first endpoint to be mainnet.base.org, got %s", provider.endpoints[0])
	}
}

func TestRoundRobinProvider_Endpoint(t *testing.T) {
	provider, err := NewRoundRobinProvider(Config{
		ChainID:   "test-chain",
		Endpoints: []string{"https://endpoint1.example.com", "https://endpoint2.example.com"},
	})
	if err != nil {
		t.Fatalf("NewRoundRobinProvider() failed: %v", err)
	}

	// Initial endpoint should be first
	first := provider.Endpoint()
	if first != "https://endpoint1.example.com" {
		t.Errorf("expected first endpoint, got %s", first)
	}

	// After nextEndpoint, should be second
	provider.nextEndpoint()
	second := provider.Endpoint()
	if second != "https://endpoint2.example.com" {
		t.Errorf("expected second endpoint, got %s", second)
	}
}

func TestDefaultEndpoints(t *testing.T) {
	// Verify Base endpoints are defined
	if len(BaseEndpoints) == 0 {
		t.Error("BaseEndpoints should not be empty")
	}

	// Verify Base Sepolia endpoints are defined
	if len(BaseSepoliaEndpoints) == 0 {
		t.Error("BaseSepoliaEndpoints should not be empty")
	}

	// Verify Ethereum endpoints are defined
	if len(EthEndpoints) == 0 {
		t.Error("EthEndpoints should not be empty")
	}

	// Verify Solana endpoints are defined
	if len(SolanaEndpoints) == 0 {
		t.Error("SolanaEndpoints should not be empty")
	}
}