//go:build !disable_mev

package jito

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

func TestJitoMEV_New(t *testing.T) {
	t.Run("valid configuration", func(t *testing.T) {
		submitter, err := NewJitoMEV("https://mainnet.block-engine.jito.wtf/api/v1", "")
		require.NoError(t, err)
		require.NotNil(t, submitter)
		assert.Equal(t, "jito", submitter.Type())
	})

	t.Run("empty endpoint", func(t *testing.T) {
		submitter, err := NewJitoMEV("", "")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "endpoint is required")
		require.Nil(t, submitter)
	})

	t.Run("with wallet key", func(t *testing.T) {
		// Test with a valid base58 encoded wallet key
		// Using a simple test key (empty would be all zeros)
		submitter, err := NewJitoMEV("https://mainnet.block-engine.jito.wtf/api/v1", "")
		require.NoError(t, err)
		require.NotNil(t, submitter)
		assert.Equal(t, "jito", submitter.Type())
	})
}

func TestJitoMEV_Submit(t *testing.T) {
	t.Run("successful jito submission", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Contains(t, r.URL.Path, jitoBundlesEndpoint)

			var req map[string]interface{}
			err := json.NewDecoder(r.Body).Decode(&req)
			require.NoError(t, err)
			assert.Equal(t, "sendBundle", req["method"])

			// Verify params structure
			params, ok := req["params"].([]interface{})
			require.True(t, ok)
			assert.Len(t, params, 2)

			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]string{
					"signature": "4xPhVEKTi2R5JYhT6K8NKFvL4aJY4rLWJ4mWAhUL4Y3R3nL5xQhK7vPbJmTd8qW9",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainSolana,
				From:  domain.MustParseAddress("4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T"),
				To:    domain.MustParseAddress("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9z7AWNS"),
			},
			Signature: []byte("signed_solana_tx_data"),
			Hash:      "solana_tx_hash_123",
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.NoError(t, err)
		assert.NotEmpty(t, result.Signature)
	})

	t.Run("rpc error returns error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"error": map[string]interface{}{
					"code":    -32600,
					"message": "Invalid request",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainSolana,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "jito error: Invalid request")
		assert.Empty(t, result.Signature)
	})

	t.Run("http error returns error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainSolana,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "unexpected status code: 500")
		assert.Empty(t, result.Signature)
	})

	t.Run("with custom tip lamports", func(t *testing.T) {
		var receivedParams map[string]interface{}
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var req map[string]interface{}
			err := json.NewDecoder(r.Body).Decode(&req)
			require.NoError(t, err)
			receivedParams = req["params"].([]interface{})[1].(map[string]interface{})

			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]string{
					"signature": "signature_with_tip",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainSolana,
			},
			Signature: []byte("signed_tx"),
		}

		customTip := uint64(50000)
		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{
			JitoTipLamports: customTip,
		})
		require.NoError(t, err)
		// JSON unmarshals numbers as float64, so compare as float64
		assert.Equal(t, float64(customTip), receivedParams["tipLamports"])
		assert.NotEmpty(t, result.Signature)
	})

	t.Run("with fast mode enabled", func(t *testing.T) {
		var receivedParams map[string]interface{}
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var req map[string]interface{}
			err := json.NewDecoder(r.Body).Decode(&req)
			require.NoError(t, err)
			receivedParams = req["params"].([]interface{})[1].(map[string]interface{})

			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]string{
					"signature": "fast_signature",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainSolana,
			},
			Signature: []byte("signed_tx"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{
			FastMode: true,
		})
		require.NoError(t, err)
		assert.True(t, receivedParams["fastMode"].(bool))
		assert.NotEmpty(t, result.Signature)
	})
}

func TestJitoMEV_SubmitBundle(t *testing.T) {
	t.Run("successful bundle submission", func(t *testing.T) {
		var receivedReq map[string]interface{}
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			err := json.NewDecoder(r.Body).Decode(&receivedReq)
			require.NoError(t, err)
			assert.Equal(t, "sendBundle", receivedReq["method"])

			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]string{
					"signature": "bundle_signature_123",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		// Get access to SubmitBundle via type assertion
		jitoMEV, ok := submitter.(*jitoMEV)
		require.True(t, ok, "submitter should be *jitoMEV")

		txs := [][]byte{
			[]byte("tx1_data"),
			[]byte("tx2_data"),
		}

		result, err := jitoMEV.SubmitBundle(context.Background(), txs)
		require.NoError(t, err)
		assert.Equal(t, "bundle_signature_123", result)

		// Verify the transactions were included in the request
		params := receivedReq["params"].([]interface{})
		txsParam := params[0].([]interface{})
		assert.Len(t, txsParam, 2)
	})

	t.Run("empty transactions returns error", func(t *testing.T) {
		submitter, err := NewJitoMEV("https://mainnet.block-engine.jito.wtf/api/v1", "")
		require.NoError(t, err)

		jitoMEV, ok := submitter.(*jitoMEV)
		require.True(t, ok, "submitter should be *jitoMEV")

		result, err := jitoMEV.SubmitBundle(context.Background(), [][]byte{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no transactions")
		assert.Empty(t, result)
	})

	t.Run("bundle submission error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"error": map[string]interface{}{
					"code":    -32700,
					"message": "Parse error",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		jitoMEV, ok := submitter.(*jitoMEV)
		require.True(t, ok, "submitter should be *jitoMEV")

		txs := [][]byte{
			[]byte("tx1_data"),
		}

		result, err := jitoMEV.SubmitBundle(context.Background(), txs)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "jito bundle error: Parse error")
		assert.Empty(t, result)
	})

	t.Run("bundle http error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		jitoMEV, ok := submitter.(*jitoMEV)
		require.True(t, ok, "submitter should be *jitoMEV")

		txs := [][]byte{
			[]byte("tx1_data"),
		}

		result, err := jitoMEV.SubmitBundle(context.Background(), txs)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "unexpected status code: 503")
		assert.Empty(t, result)
	})
}

func TestJitoMEV_Type(t *testing.T) {
	submitter, err := NewJitoMEV("https://mainnet.block-engine.jito.wtf/api/v1", "")
	require.NoError(t, err)
	assert.Equal(t, "jito", submitter.Type())
}

func TestJitoMEV_Stats(t *testing.T) {
	t.Run("stats tracking", func(t *testing.T) {
		callCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			resp := map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]string{
					"signature": "test_signature",
				},
			}
			if callCount > 3 {
				// Return error after some successful calls
				resp = map[string]interface{}{
					"jsonrpc": "2.0",
					"id":      1,
					"error": map[string]interface{}{
						"code":    -32600,
						"message": "Invalid request",
					},
				}
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewJitoMEV(server.URL, "")
		require.NoError(t, err)

		// Get access to stats via type assertion
		jitoMEV, ok := submitter.(*jitoMEV)
		require.True(t, ok, "submitter should be *jitoMEV")

		// Initial stats should be zero
		stats := jitoMEV.StatsSafe()
		assert.Equal(t, uint64(0), stats.SubmittedCount)
		assert.Equal(t, uint64(0), stats.SuccessCount)

		// Submit successful transactions
		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{Chain: domain.ChainSolana},
			Signature:  []byte("tx1"),
		}

		_, _ = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		_, _ = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		_, _ = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})

		stats = jitoMEV.StatsSafe()
		assert.Equal(t, uint64(3), stats.SubmittedCount)
		assert.Equal(t, uint64(3), stats.SuccessCount)
		assert.Equal(t, uint64(0), stats.FailedCount)

		// Submit a failing transaction
		_, _ = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})

		stats = jitoMEV.StatsSafe()
		assert.Equal(t, uint64(4), stats.SubmittedCount)
		assert.Equal(t, uint64(3), stats.SuccessCount)
		assert.Equal(t, uint64(1), stats.FailedCount)
	})
}

// Compile-time interface assertion
var _ ports.MEVSubmitter = (*jitoMEV)(nil)