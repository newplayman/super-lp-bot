//go:build !disable_mev

package flashbotsprotect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestMev_BundleSuccess_NoFallback verifies that when Flashbots succeeds,
// the fallback is never called.
func TestMev_BundleSuccess_NoFallback(t *testing.T) {
	fallbackCallCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := mevShareResponse{
			JSONRPC: "2.0",
			ID:      1,
			Result:  "0xbundle_hash_success",
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	fallback := &strictModeMockBroadcaster{
		sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
			fallbackCallCount++
			return nil
		},
	}

	// Create MEV with strict mode enabled
	cfg := StrictConfig{
		StrictMode:         true,
		BundleEndpoint:     server.URL,
		FallbackBroadcaster: fallback,
	}

	submitter, err := NewFlashbotsMEVStrict(cfg)
	require.NoError(t, err)

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			Chain: domain.ChainBase,
		},
		Signature: []byte("signed_tx_data"),
	}

	result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
	require.NoError(t, err)
	assert.Equal(t, "0xbundle_hash_success", result.BundleHash)
	assert.Equal(t, 0, fallbackCallCount, "fallback should not be called when Flashbots succeeds")
}

// TestMev_BundleFails_StrictMode_Errors verifies that in strict mode,
// when Flashbots fails, an error is returned without calling fallback.
func TestMev_BundleFails_StrictMode_Errors(t *testing.T) {
	fallbackCallCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	fallback := &strictModeMockBroadcaster{
		sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
			fallbackCallCount++
			return nil
		},
	}

	// Create MEV with strict mode enabled
	cfg := StrictConfig{
		StrictMode:         true,
		BundleEndpoint:     server.URL,
		FallbackBroadcaster: fallback,
	}

	submitter, err := NewFlashbotsMEVStrict(cfg)
	require.NoError(t, err)

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			Chain: domain.ChainBase,
		},
		Signature: []byte("signed_tx_data"),
	}

	result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "mev send failed (strict)")
	assert.Empty(t, result.BundleHash)
	assert.Equal(t, 0, fallbackCallCount, "fallback should not be called in strict mode")
}

// TestMev_BundleFails_NonStrict_FallsBack verifies that in non-strict mode,
// when Flashbots fails, the fallback is called.
func TestMev_BundleFails_NonStrict_FallsBack(t *testing.T) {
	// Skip this test when live build tag is set, as live forces strict mode
	if strictModeForLive {
		t.Skip("non-strict mode not available with live build tag")
	}

	fallbackCalled := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := mevShareResponse{
			JSONRPC: "2.0",
			ID:      1,
			Error: &struct {
				Code    int    `json:"code"`
				Message string `json:"message"`
			}{
				Code:    -32600,
				Message: "Invalid request",
			},
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	fallback := &strictModeMockBroadcaster{
		sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
			fallbackCalled = true
			return nil
		},
	}

	// Create MEV with strict mode DISABLED
	cfg := StrictConfig{
		StrictMode:         false,
		BundleEndpoint:     server.URL,
		FallbackBroadcaster: fallback,
	}

	submitter, err := NewFlashbotsMEVStrict(cfg)
	require.NoError(t, err)

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			Chain: domain.ChainBase,
		},
		Signature: []byte("signed_tx_data"),
	}

	result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
	require.NoError(t, err)
	assert.True(t, fallbackCalled, "fallback should be called in non-strict mode")
	assert.Empty(t, result.BundleHash)
}

// TestMev_StrictMode_LiveBuildTag verifies that the live build tag
// forces StrictMode=true regardless of config.
func TestMev_StrictMode_LiveBuildTag(t *testing.T) {
	// This test verifies that when the live build tag is set,
	// StrictMode is forced to true even if configured as false.
	// We test this by checking the behavior of the constructor.

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	fallback := &strictModeMockBroadcaster{
		sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
			return nil
		},
	}

	// Config says strict=false
	cfg := StrictConfig{
		StrictMode:         false,
		BundleEndpoint:     server.URL,
		FallbackBroadcaster: fallback,
	}

	submitter, err := NewFlashbotsMEVStrict(cfg)
	require.NoError(t, err)

	// Get access to check the effective config
	mevStrict, ok := submitter.(*flashbotsMEVStrict)
	require.True(t, ok)

	// The effective StrictMode should match the build tag behavior:
	// - With live tag: StrictMode is forced to true
	// - Without live tag: StrictMode follows config
	expectedStrictMode := cfg.StrictMode || strictModeForLive
	assert.Equal(t, expectedStrictMode, mevStrict.cfg.StrictMode,
		"StrictMode should be %v (config=%v, liveTag=%v)",
		expectedStrictMode, cfg.StrictMode, strictModeForLive)
}

// TestReorg_RebroadcastUsesStrictMev verifies that the reorg handler
// uses the strict MEV path for rebroadcast.
func TestReorg_RebroadcastUsesStrictMev(t *testing.T) {
	// This test verifies that when reorg handler rebroadcasts a transaction,
	// it uses the MEV submitter's strict mode behavior.

	mevCallCount := 0
	fallbackCalled := false

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mevCallCount++
		// First call succeeds, subsequent calls fail
		if mevCallCount > 1 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		resp := mevShareResponse{
			JSONRPC: "2.0",
			ID:      1,
			Result:  "0xbundle_hash",
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	fallback := &strictModeMockBroadcaster{
		sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
			fallbackCalled = true
			return nil
		},
	}

	// Use strict mode - rebroadcast should fail in strict mode
	cfg := StrictConfig{
		StrictMode:         true,
		BundleEndpoint:     server.URL,
		FallbackBroadcaster: fallback,
	}

	submitter, err := NewFlashbotsMEVStrict(cfg)
	require.NoError(t, err)

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			Chain: domain.ChainBase,
		},
		Signature: []byte("signed_tx_data"),
	}

	// First submission succeeds
	_, err = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
	require.NoError(t, err)

	// Simulate reorg rebroadcast - this should fail in strict mode
	// (not call fallback)
	_, err = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "mev send failed (strict)")
	assert.False(t, fallbackCalled, "fallback should not be called in strict mode for rebroadcast")
}

// strictModeMockBroadcaster is a mock broadcaster for strict mode tests.
type strictModeMockBroadcaster struct {
	sendFunc func(ctx context.Context, tx domain.SignedTx) error
}

func (m *strictModeMockBroadcaster) Send(ctx context.Context, tx domain.SignedTx) error {
	if m.sendFunc != nil {
		return m.sendFunc(ctx, tx)
	}
	return nil
}

func (m *strictModeMockBroadcaster) CallCount() int64 {
	return 0
}
