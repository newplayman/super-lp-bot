//go:build !disable_mev

// Package flashbotsprotect implements the Flashbots Protect MEV protection adapter for lp-bot.
//
// This adapter submits transactions through Flashbots Protect API (mev-share) to protect
// against front-running and sandwich attacks on Base/EVM chains.
//
// The adapter is NOT compiled into dryrun/shadow builds (build tag !disable_mev
// ensures it is excluded when MEV protection is disabled).
//
// Flashbots Protect API documentation:
// https://docs.flashbots.net/flashbots-protect/rpc/quick-start
package flashbotsprotect

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync/atomic"
	"time"

	"go.uber.org/zap"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Build-time flags
var (
	// strictModeForLive is set to true when the live build tag is enabled.
	// This forces StrictMode=true regardless of config.
	strictModeForLive = false
)

// API endpoints for Flashbots Protect mev-share
const (
	// mevShareEndpoint submits a transaction to the mev-share endpoint
	mevShareEndpoint = "/rpc"

	// defaultTimeout is the default HTTP request timeout
	defaultTimeout = 30 * time.Second
)

// StrictConfig contains the configuration for MEV submission with strict mode support.
type StrictConfig struct {
	// StrictMode controls fallback behavior when Flashbots submission fails.
	// When true (default): returns error on Flashbots failure, never falls back to public mempool.
	// When false: falls back to public mempool if Flashbots fails.
	StrictMode bool

	// BundleEndpoint is the Flashbots RPC URL
	BundleEndpoint string

	// ApiKey is the optional Flashbots API key
	ApiKey string

	// FallbackBroadcaster is the broadcaster to use when StrictMode is false
	// and Flashbots submission fails. Can be nil.
	FallbackBroadcaster ports.Broadcaster

	// Logger for warning messages when falling back (non-strict mode only)
	Logger *zap.Logger
}

// MEVStats holds submission statistics for monitoring.
type MEVStats struct {
	// SubmittedCount is the total number of transactions submitted to MEV relay
	SubmittedCount uint64

	// SuccessCount is the number of successful MEV submissions
	SuccessCount uint64

	// FallbackCount is the number of submissions that fell back to direct broadcast
	FallbackCount uint64

	// FailedCount is the number of failed submissions (both MEV and fallback failed)
	FailedCount uint64
}

// flashbotsMEVStrict implements the ports.MEVSubmitter interface with strict mode support.
type flashbotsMEVStrict struct {
	httpClient *http.Client
	rpcURL     string
	apiKey     string
	fallback   ports.Broadcaster
	cfg        StrictConfig

	// Stats counters
	submittedCount atomic.Uint64
	successCount   atomic.Uint64
	fallbackCount  atomic.Uint64
	failedCount    atomic.Uint64
}

// NewFlashbotsMEVStrict creates a new Flashbots MEV submitter with strict mode support.
//
// Parameters:
//   - cfg: StrictConfig containing RPC URL, API key, fallback broadcaster, and strict mode setting
//
// Returns a configured MEVSubmitter or an error if configuration is invalid.
// When the live build tag is set, StrictMode is forced to true regardless of config.
func NewFlashbotsMEVStrict(cfg StrictConfig) (ports.MEVSubmitter, error) {
	if cfg.BundleEndpoint == "" {
		return nil, errors.New("bundle endpoint is required for Flashbots MEV")
	}

	// Force strict mode if live build tag is set
	if strictModeForLive {
		cfg.StrictMode = true
	}

	client := &http.Client{
		Timeout: defaultTimeout,
	}

	return &flashbotsMEVStrict{
		httpClient: client,
		rpcURL:     cfg.BundleEndpoint,
		apiKey:     cfg.ApiKey,
		fallback:   cfg.FallbackBroadcaster,
		cfg:        cfg,
	}, nil
}

// Submit submits a signed transaction to Flashbots Protect with strict mode support.
//
// In strict mode (default): Returns error if Flashbots submission fails.
// In non-strict mode: Falls back to public mempool if Flashbots fails.
func (m *flashbotsMEVStrict) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	m.submittedCount.Add(1)

	result, err := m.submitToFlashbotsStrict(ctx, tx, opts)
	if err == nil {
		// Flashbots submission succeeded
		m.successCount.Add(1)
		return ports.MEVSubmissionResult{
			BundleHash: result,
		}, nil
	}

	// Flashbots submission failed
	m.failedCount.Add(1)

	if m.cfg.StrictMode {
		// In strict mode: return error, never fall back to public mempool
		return ports.MEVSubmissionResult{}, fmt.Errorf("mev send failed (strict): %w", err)
	}

	// In non-strict mode: warn and fall back to public mempool
	if m.cfg.Logger != nil {
		m.cfg.Logger.Warn("mev fallback to public mempool", zap.Error(err))
	}

	// Try fallback
	if m.fallback != nil {
		fallbackErr := m.fallback.Send(ctx, tx)
		if fallbackErr != nil {
			return ports.MEVSubmissionResult{}, fmt.Errorf("mev send failed: %w, fallback: %v", err, fallbackErr)
		}
		// Fallback succeeded
		m.fallbackCount.Add(1)
		return ports.MEVSubmissionResult{
			BundleHash: "", // No bundle hash from fallback
		}, nil
	}

	// No fallback available
	return ports.MEVSubmissionResult{}, fmt.Errorf("mev send failed (strict): %w", err)
}

// submitToFlashbotsStrict submits a transaction to the Flashbots mev-share endpoint.
func (m *flashbotsMEVStrict) submitToFlashbotsStrict(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (string, error) {
	// For single transactions, use eth_sendPrivateTransaction
	params := ethSendPrivateTransactionParams{
		Tx: "0x" + hex.EncodeToString(bytes.TrimPrefix(tx.Signature, []byte("0x"))),
		Preferences: &struct {
			Fast          bool   `json:"fast,omitempty"`
			MaxBlockNumber uint64 `json:"maxBlockNumber,omitempty"`
			ValidityStatus string `json:"validityStatus,omitempty"`
			Builders      []string `json:"builders,omitempty"`
		}{
			Fast: opts.MaxBundleGasLimit > 0, // Use fast mode if gas limit specified
		},
	}

	paramsJSON, err := json.Marshal([]interface{}{params})
	if err != nil {
		return "", fmt.Errorf("failed to marshal params: %w", err)
	}

	req := mevShareRequest{
		JSONRPC: "2.0",
		Method:  "eth_sendPrivateTransaction",
		Params:  paramsJSON,
		ID:      1,
	}

	var resp mevShareResponse
	if err := m.doRPCStrict(ctx, req, &resp); err != nil {
		return "", fmt.Errorf("flashbots RPC call failed: %w", err)
	}

	if resp.Error != nil {
		return "", fmt.Errorf("flashbots error: %s (code %d)", resp.Error.Message, resp.Error.Code)
	}

	return resp.Result, nil
}

// doRPCStrict performs an RPC call to the Flashbots mev-share endpoint for strict mode.
func (m *flashbotsMEVStrict) doRPCStrict(ctx context.Context, req mevShareRequest, resp *mevShareResponse) error {
	reqJSON, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, m.rpcURL+mevShareEndpoint, bytes.NewReader(reqJSON))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	if m.apiKey != "" {
		httpReq.Header.Set("X-Flashbots-Api-Key", m.apiKey)
	}

	httpResp, err := m.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("HTTP request failed: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	if err := json.NewDecoder(httpResp.Body).Decode(resp); err != nil {
		return fmt.Errorf("failed to decode response: %w", err)
	}

	return nil
}

// Stats returns the current submission statistics for strict mode MEV.
func (m *flashbotsMEVStrict) Stats(ctx context.Context) (*MEVStats, error) {
	return &MEVStats{
		SubmittedCount: m.submittedCount.Load(),
		SuccessCount:  m.successCount.Load(),
		FallbackCount: m.fallbackCount.Load(),
		FailedCount:   m.failedCount.Load(),
	}, nil
}

// StatsSafe returns the current submission statistics without requiring context.
func (m *flashbotsMEVStrict) StatsSafe() *MEVStats {
	return &MEVStats{
		SubmittedCount: m.submittedCount.Load(),
		SuccessCount:  m.successCount.Load(),
		FallbackCount: m.fallbackCount.Load(),
		FailedCount:   m.failedCount.Load(),
	}
}

// Type returns the type identifier for this MEV submitter.
func (m *flashbotsMEVStrict) Type() string {
	return "flashbots"
}

// Compile-time interface assertion for flashbotsMEVStrict
var _ ports.MEVSubmitter = (*flashbotsMEVStrict)(nil)

// flashbotsMEV implements the ports.MEVSubmitter interface for Flashbots MEV protection.
type flashbotsMEV struct {
	httpClient *http.Client
	rpcURL     string
	apiKey     string
	fallback   ports.Broadcaster

	// Stats counters
	submittedCount atomic.Uint64
	successCount   atomic.Uint64
	fallbackCount  atomic.Uint64
	failedCount    atomic.Uint64
}

// NewFlashbotsMEV creates a new Flashbots MEV submitter instance.
//
// Parameters:
//   - rpcURL: Flashbots Protect RPC URL (e.g., "https://rpc.mev-share.holesky.flashbots.net")
//   - apiKey: Optional API key for Flashbots Protect
//   - fallback: Broadcaster to use if Flashbots submission fails
//
// Returns a configured MEVSubmitter or an error if configuration is invalid.
func NewFlashbotsMEV(rpcURL, apiKey string, fallback ports.Broadcaster) (ports.MEVSubmitter, error) {
	if rpcURL == "" {
		return nil, errors.New("rpcURL is required for Flashbots MEV")
	}

	client := &http.Client{
		Timeout: defaultTimeout,
	}

	return &flashbotsMEV{
		httpClient: client,
		rpcURL:     rpcURL,
		apiKey:     apiKey,
		fallback:   fallback,
	}, nil
}

// mevShareRequest represents a request to the mev-share endpoint.
type mevShareRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
	ID      int             `json:"id"`
}

// mevShareResponse represents a response from the mev-share endpoint.
type mevShareResponse struct {
	JSONRPC string `json:"jsonrpc"`
	ID      int    `json:"id"`
	Result  string `json:"result,omitempty"`
	Error   *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

// ethSendBundleParams represents parameters for eth_sendBundle.
type ethSendBundleParams struct {
	Txs               []string `json:"txs"`
	BlockNumber       string   `json:"blockNumber,omitempty"`
	MinTimestamp      uint64   `json:"minTimestamp,omitempty"`
	MaxTimestamp      uint64   `json:"maxTimestamp,omitempty"`
	RevertingHashes   []string `json:"revertingHashes,omitempty"`
	UUID              string   `json:"uuid,omitempty"`
	Preferences       *struct {
		Fast bool `json:"fast,omitempty"`
	} `json:"preferences,omitempty"`
}

// ethSendPrivateTransactionParams represents parameters for eth_sendPrivateTransaction.
type ethSendPrivateTransactionParams struct {
	Tx           string `json:"tx"`
	Preferences  *struct {
		Fast                    bool   `json:"fast,omitempty"`
		MaxBlockNumber          uint64 `json:"maxBlockNumber,omitempty"`
		ValidityStatus          string `json:"validityStatus,omitempty"`
		Builders                []string `json:"builders,omitempty"`
	} `json:"preferences,omitempty"`
}

// Submit submits a signed transaction to Flashbots Protect for MEV-protected execution.
//
// If Flashbots submission fails, it falls back to the configured Broadcaster.
// Falls back to direct broadcast if Flashbots fails (as per spec §6.7).
func (m *flashbotsMEV) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	m.submittedCount.Add(1)

	result, err := m.submitToFlashbots(ctx, tx, opts)
	if err != nil {
		// Try fallback if available
		if m.fallback != nil {
			fallbackErr := m.fallback.Send(ctx, tx)
			if fallbackErr != nil {
				m.failedCount.Add(1)
				return ports.MEVSubmissionResult{}, fmt.Errorf("flashbots: %w, fallback: %v", err, fallbackErr)
			}
			// Fallback succeeded
			m.fallbackCount.Add(1)
			return ports.MEVSubmissionResult{
				BundleHash: "", // No bundle hash from fallback
			}, nil
		}
		// No fallback available
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("flashbots submit failed: %w", err)
	}

	// Flashbots submission succeeded
	m.successCount.Add(1)
	return ports.MEVSubmissionResult{
		BundleHash: result,
	}, nil
}

// submitToFlashbots submits a transaction to the Flashbots mev-share endpoint.
func (m *flashbotsMEV) submitToFlashbots(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (string, error) {
	// For single transactions, use eth_sendPrivateTransaction
	params := ethSendPrivateTransactionParams{
		Tx: "0x" + hex.EncodeToString(bytes.TrimPrefix(tx.Signature, []byte("0x"))),
		Preferences: &struct {
			Fast          bool   `json:"fast,omitempty"`
			MaxBlockNumber uint64 `json:"maxBlockNumber,omitempty"`
			ValidityStatus string `json:"validityStatus,omitempty"`
			Builders      []string `json:"builders,omitempty"`
		}{
			Fast: opts.MaxBundleGasLimit > 0, // Use fast mode if gas limit specified
		},
	}

	paramsJSON, err := json.Marshal([]interface{}{params})
	if err != nil {
		return "", fmt.Errorf("failed to marshal params: %w", err)
	}

	req := mevShareRequest{
		JSONRPC: "2.0",
		Method:  "eth_sendPrivateTransaction",
		Params:  paramsJSON,
		ID:      1,
	}

	var resp mevShareResponse
	if err := m.doRPC(ctx, req, &resp); err != nil {
		return "", fmt.Errorf("flashbots RPC call failed: %w", err)
	}

	if resp.Error != nil {
		return "", fmt.Errorf("flashbots error: %s (code %d)", resp.Error.Message, resp.Error.Code)
	}

	return resp.Result, nil
}

// SubmitBundle submits a bundle of transactions to Flashbots.
//
// This is used for batch submissions where multiple transactions should be
// executed atomically in the same block.
func (m *flashbotsMEV) SubmitBundle(ctx context.Context, txs [][]byte) (string, error) {
	m.submittedCount.Add(1)

	// Convert raw txs to hex strings
	txStrings := make([]string, len(txs))
	for i, tx := range txs {
		txStrings[i] = "0x" + hex.EncodeToString(bytes.TrimPrefix(tx, []byte("0x")))
	}

	params := ethSendBundleParams{
		Txs: txStrings,
		Preferences: &struct {
			Fast bool `json:"fast,omitempty"`
		}{
			Fast: true, // Bundles are typically submitted with fast preference
		},
	}

	paramsJSON, err := json.Marshal([]interface{}{params})
	if err != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("failed to marshal bundle params: %w", err)
	}

	req := mevShareRequest{
		JSONRPC: "2.0",
		Method:  "eth_sendBundle",
		Params:  paramsJSON,
		ID:      1,
	}

	var resp mevShareResponse
	if err := m.doRPC(ctx, req, &resp); err != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("flashbots bundle RPC call failed: %w", err)
	}

	if resp.Error != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("flashbots bundle error: %s (code %d)", resp.Error.Message, resp.Error.Code)
	}

	m.successCount.Add(1)
	return resp.Result, nil
}

// Stats returns the current submission statistics.
func (m *flashbotsMEV) Stats(ctx context.Context) (*MEVStats, error) {
	return &MEVStats{
		SubmittedCount: m.submittedCount.Load(),
		SuccessCount:  m.successCount.Load(),
		FallbackCount: m.fallbackCount.Load(),
		FailedCount:   m.failedCount.Load(),
	}, nil
}

// StatsSafe returns the current submission statistics without requiring context.
func (m *flashbotsMEV) StatsSafe() *MEVStats {
	return &MEVStats{
		SubmittedCount: m.submittedCount.Load(),
		SuccessCount:  m.successCount.Load(),
		FallbackCount: m.fallbackCount.Load(),
		FailedCount:   m.failedCount.Load(),
	}
}

// doRPC performs an RPC call to the Flashbots mev-share endpoint.
func (m *flashbotsMEV) doRPC(ctx context.Context, req mevShareRequest, resp *mevShareResponse) error {
	reqJSON, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, m.rpcURL+mevShareEndpoint, bytes.NewReader(reqJSON))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	if m.apiKey != "" {
		httpReq.Header.Set("X-Flashbots-Api-Key", m.apiKey)
	}

	httpResp, err := m.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("HTTP request failed: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	if err := json.NewDecoder(httpResp.Body).Decode(resp); err != nil {
		return fmt.Errorf("failed to decode response: %w", err)
	}

	return nil
}

// Type returns the type identifier for this MEV submitter.
func (m *flashbotsMEV) Type() string {
	return "flashbots"
}