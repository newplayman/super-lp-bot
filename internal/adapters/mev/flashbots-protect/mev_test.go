//go:build !disable_mev

package flashbotsprotect

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// broadcasterMock is a mock implementation of ports.Broadcaster for testing.
type broadcasterMock struct {
	sendFunc  func(ctx context.Context, tx domain.SignedTx) error
	callCount int64
}

func (m *broadcasterMock) Send(ctx context.Context, tx domain.SignedTx) error {
	if m.sendFunc != nil {
		return m.sendFunc(ctx, tx)
	}
	return nil
}

func (m *broadcasterMock) CallCount() int64 {
	return m.callCount
}

func TestFlashbotsMEV_New(t *testing.T) {
	t.Run("valid configuration", func(t *testing.T) {
		submitter, err := NewFlashbotsMEV("https://rpc.mev-share.holesky.flashbots.net", "test-key", nil)
		require.NoError(t, err)
		require.NotNil(t, submitter)
		assert.Equal(t, "flashbots", submitter.Type())
	})

	t.Run("empty rpc url", func(t *testing.T) {
		submitter, err := NewFlashbotsMEV("", "test-key", nil)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "rpcURL is required")
		require.Nil(t, submitter)
	})

	t.Run("with fallback broadcaster", func(t *testing.T) {
		fallback := &broadcasterMock{}
		submitter, err := NewFlashbotsMEV("https://rpc.mev-share.holesky.flashbots.net", "test-key", fallback)
		require.NoError(t, err)
		require.NotNil(t, submitter)
	})
}

func TestFlashbotsMEV_Submit(t *testing.T) {
	t.Run("successful flashbots submission", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Contains(t, r.URL.Path, mevShareEndpoint)

			var req mevShareRequest
			err := json.NewDecoder(r.Body).Decode(&req)
			require.NoError(t, err)
			assert.Equal(t, "eth_sendPrivateTransaction", req.Method)

			resp := mevShareResponse{
				JSONRPC: "2.0",
				ID:      1,
				Result:  "0xbundle_hash_123",
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
				From:  domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
				To:    domain.MustParseAddress("0x0987654321098765432109876543210987654321"),
			},
			Signature: []byte("signed_tx_data"),
			Hash:      "0xtxhash123",
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.NoError(t, err)
		assert.Equal(t, "0xbundle_hash_123", result.BundleHash)
	})

	t.Run("rpc error returns error", func(t *testing.T) {
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

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "flashbots error: Invalid request")
		assert.Empty(t, result.BundleHash)
	})

	t.Run("http error returns error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "unexpected status code: 500")
		assert.Empty(t, result.BundleHash)
	})
}

func TestFlashbotsMEV_Submit_Fallback(t *testing.T) {
	t.Run("fallback on flashbots failure", func(t *testing.T) {
		fallbackCalled := false
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		fallback := &broadcasterMock{
			sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
				fallbackCalled = true
				return nil
			},
		}

		submitter, err := NewFlashbotsMEV(server.URL, "", fallback)
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.NoError(t, err)
		assert.True(t, fallbackCalled, "fallback should have been called")
		assert.Empty(t, result.BundleHash)
	})

	t.Run("both flashbots and fallback fail", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		fallback := &broadcasterMock{
			sendFunc: func(ctx context.Context, tx domain.SignedTx) error {
				return errors.New("fallback error")
			},
		}

		submitter, err := NewFlashbotsMEV(server.URL, "", fallback)
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "flashbots: ")
		assert.Contains(t, err.Error(), "fallback: ")
		assert.Empty(t, result.BundleHash)
	})

	t.Run("no fallback available", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
			},
			Signature: []byte("signed_tx_data"),
		}

		result, err := submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})
		require.Error(t, err)
		assert.Contains(t, err.Error(), "flashbots submit failed:")
		assert.Empty(t, result.BundleHash)
	})
}

func TestFlashbotsMEV_Stats(t *testing.T) {
	t.Run("stats via type assertion", func(t *testing.T) {
		callCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			if callCount == 1 {
				resp := mevShareResponse{
					JSONRPC: "2.0",
					ID:      1,
					Result:  "0xbundle_hash",
				}
				json.NewEncoder(w).Encode(resp)
			} else {
				// Return error on second call to test failure count
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
			}
		}))
		defer server.Close()

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		// Get stats via type assertion
		mevWithStats, ok := submitter.(*flashbotsMEV)
		require.True(t, ok, "submitter should be *flashbotsMEV")

		// Initial stats should be zero
		stats := mevWithStats.StatsSafe()
		assert.Equal(t, uint64(0), stats.SubmittedCount)
		assert.Equal(t, uint64(0), stats.SuccessCount)

		// Submit a successful tx
		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{Chain: domain.ChainBase},
			Signature:  []byte("tx1"),
		}
		_, _ = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})

		stats = mevWithStats.StatsSafe()
		assert.Equal(t, uint64(1), stats.SubmittedCount)
		assert.Equal(t, uint64(1), stats.SuccessCount)
		assert.Equal(t, uint64(0), stats.FailedCount)

		// Submit another that will fail
		_, _ = submitter.Submit(context.Background(), tx, ports.MEVSubmitOpts{})

		stats = mevWithStats.StatsSafe()
		assert.Equal(t, uint64(2), stats.SubmittedCount)
		assert.Equal(t, uint64(1), stats.SuccessCount)
		assert.Equal(t, uint64(1), stats.FailedCount)
	})
}

func TestFlashbotsMEV_SubmitBundle(t *testing.T) {
	t.Run("successful bundle submission", func(t *testing.T) {
		var receivedReq mevShareRequest
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			err := json.NewDecoder(r.Body).Decode(&receivedReq)
			require.NoError(t, err)
			assert.Equal(t, "eth_sendBundle", receivedReq.Method)

			resp := mevShareResponse{
				JSONRPC: "2.0",
				ID:      1,
				Result:  "0xbundle_hash_456",
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		// Get access to SubmitBundle via type assertion
		mevWithBundle, ok := submitter.(*flashbotsMEV)
		require.True(t, ok, "submitter should be *flashbotsMEV")

		txs := [][]byte{
			[]byte("tx1_data"),
			[]byte("tx2_data"),
		}

		result, err := mevWithBundle.SubmitBundle(context.Background(), txs)
		require.NoError(t, err)
		assert.Equal(t, "0xbundle_hash_456", result)
	})

	t.Run("bundle submission error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			resp := mevShareResponse{
				JSONRPC: "2.0",
				ID:      1,
				Error: &struct {
					Code    int    `json:"code"`
					Message string `json:"message"`
				}{
					Code:    -32700,
					Message: "Parse error",
				},
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		submitter, err := NewFlashbotsMEV(server.URL, "", nil)
		require.NoError(t, err)

		mevWithBundle, ok := submitter.(*flashbotsMEV)
		require.True(t, ok, "submitter should be *flashbotsMEV")

		txs := [][]byte{
			[]byte("tx1_data"),
		}

		result, err := mevWithBundle.SubmitBundle(context.Background(), txs)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "flashbots bundle error: Parse error")
		assert.Empty(t, result)
	})
}

func TestFlashbotsMEV_Type(t *testing.T) {
	submitter, err := NewFlashbotsMEV("https://rpc.mev-share.holesky.flashbots.net", "", nil)
	require.NoError(t, err)
	assert.Equal(t, "flashbots", submitter.Type())
}

// Compile-time interface assertion
var _ ports.MEVSubmitter = (*flashbotsMEV)(nil)