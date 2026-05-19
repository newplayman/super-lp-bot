//go:build !disable_mev

// Package jito implements the Jito MEV protection adapter for lp-bot.
//
// This adapter submits transactions through Jito blockengine to protect
// against front-running and sandwich attacks on Solana.
//
// The adapter is NOT compiled into dryrun/shadow builds (build tag !disable_mev
// ensures it is excluded when MEV protection is disabled).
//
// Jito Blockengine API documentation:
// https://docs.jito.wtf/docs/welcome
package jito

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync/atomic"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// API endpoints for Jito Blockengine
const (
	// jitoBundlesEndpoint submits a bundle of transactions
	jitoBundlesEndpoint = "/api/v1/bundles"

	// jitoTipAccountsEndpoint returns available tip accounts
	jitoTipAccountsEndpoint = "/api/v1/tip/accounts"

	// defaultTimeout is the default HTTP request timeout
	defaultTimeout = 30 * time.Second
)

// JitoStats holds submission statistics for monitoring.
type JitoStats struct {
	// SubmittedCount is the total number of transactions submitted to Jito
	SubmittedCount uint64

	// SuccessCount is the number of successful Jito submissions
	SuccessCount uint64

	// FailedCount is the number of failed submissions
	FailedCount uint64
}

// jitoMEV implements the ports.MEVSubmitter interface for Jito MEV protection.
type jitoMEV struct {
	httpClient *http.Client
	endpoint   string
	wallet     []byte // wallet private key for signing

	// Stats counters
	submittedCount atomic.Uint64
	successCount   atomic.Uint64
	failedCount    atomic.Uint64
}

// jitoBundleRequest represents a request to the Jito bundles endpoint.
type jitoBundleRequest struct {
	JSONRPC string `json:"jsonrpc"`
	Method  string `json:"method"`
	Params  struct {
		Tx       string `json:"tx"`
		Tip      uint64 `json:"tip"`
		FastMode bool   `json:"fastMode"`
	} `json:"params"`
	ID int `json:"id"`
}

// jitoBundleResponse represents a response from the Jito bundles endpoint.
type jitoBundleResponse struct {
	JSONRPC string `json:"jsonrpc"`
	ID      int    `json:"id"`
	Result  struct {
		Signature string `json:"signature"`
	} `json:"result,omitempty"`
	Error *jitoError `json:"error,omitempty"`
}

// jitoError represents an error from the Jito API.
type jitoError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// NewJitoMEV creates a new Jito MEV submitter instance.
//
// Parameters:
//   - endpoint: Jito blockengine endpoint (e.g., "https://mainnet.block-engine.jito.wtf/api/v1")
//   - walletKey: Optional wallet private key for signing (base58 encoded)
//
// Returns a configured MEVSubmitter or an error if configuration is invalid.
func NewJitoMEV(endpoint, walletKey string) (ports.MEVSubmitter, error) {
	if endpoint == "" {
		return nil, errors.New("endpoint is required for Jito MEV")
	}

	client := &http.Client{
		Timeout: defaultTimeout,
	}

	var wallet []byte
	if walletKey != "" {
		// Decode base58 wallet key if provided
		decoded, err := base58Decode(walletKey)
		if err != nil {
			return nil, fmt.Errorf("failed to decode wallet key: %w", err)
		}
		wallet = decoded
	}

	return &jitoMEV{
		httpClient: client,
		endpoint:   endpoint,
		wallet:     wallet,
	}, nil
}

// base58Decode decodes a base58 string.
func base58Decode(s string) ([]byte, error) {
	// Solana uses base58 for wallet keys
	// Using a simple implementation since we don't want external dependencies
	alphabet := "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

	// Reverse lookup map
	indices := make(map[byte]int)
	for i, c := range alphabet {
		indices[byte(c)] = i
	}

	result := make([]byte, 0)
	leadingOnes := 0

	// Count leading '1's (which represent leading zero bytes)
	for i := 0; i < len(s) && s[i] == '1'; i++ {
		leadingOnes++
	}

	// Base58 decode
	for _, c := range s[leadingOnes:] {
		idx, ok := indices[byte(c)]
		if !ok {
			return nil, errors.New("invalid base58 character")
		}

		carry := idx
		for j := len(result) - 1; j >= 0; j-- {
			carry += 58 * int(result[j])
			result[j] = byte(carry % 256)
			carry /= 256
		}

		for carry > 0 {
			result = append([]byte{byte(carry % 256)}, result...)
			carry /= 256
		}
	}

	// Add leading zeros
	for i := 0; i < leadingOnes; i++ {
		result = append([]byte{0}, result...)
	}

	return result, nil
}

// Submit submits a signed transaction to Jito blockengine for MEV-protected execution.
//
// For Solana, Jito provides MEV protection by bundling transactions and submitting
// them to validators who pay tips for priority ordering. The transaction is serialized
// and sent to the Jito blockengine which includes it in a bundle for execution.
func (m *jitoMEV) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	m.submittedCount.Add(1)

	// For Solana transactions, the signature field contains the serialized transaction bytes
	// The Hash field contains the transaction signature
	txBase64 := base64.StdEncoding.EncodeToString(tx.Signature)

	// Determine tip amount - use default if not specified
	tipLamports := opts.JitoTipLamports
	if tipLamports == 0 {
		tipLamports = 10000 // default 10000 lamports
	}

	// Build bundle request for Jito bundles API
	bundleReq := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "sendBundle",
		"params": []interface{}{
			[]string{txBase64}, // Array of base64 encoded transactions
			map[string]interface{}{
				"tipLamports": tipLamports,
				"fastMode":    opts.FastMode,
			},
		},
	}

	bundleJSON, err := json.Marshal(bundleReq)
	if err != nil {
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("failed to marshal bundle request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, m.endpoint+jitoBundlesEndpoint, bytes.NewReader(bundleJSON))
	if err != nil {
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	httpResp, err := m.httpClient.Do(httpReq)
	if err != nil {
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("HTTP request failed: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK && httpResp.StatusCode != http.StatusAccepted {
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	var resp jitoBundleResponse
	if err := json.NewDecoder(httpResp.Body).Decode(&resp); err != nil {
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("failed to decode response: %w", err)
	}

	if resp.Error != nil {
		m.failedCount.Add(1)
		return ports.MEVSubmissionResult{}, fmt.Errorf("jito error: %s (code %d)", resp.Error.Message, resp.Error.Code)
	}

	m.successCount.Add(1)
	return ports.MEVSubmissionResult{
		Signature: resp.Result.Signature,
	}, nil
}

// SubmitBundle submits a bundle of transactions to Jito blockengine.
//
// A bundle is a group of transactions that are executed atomically in the
// same order by the validator. This is useful for multi-step operations
// that need to be executed together.
func (m *jitoMEV) SubmitBundle(ctx context.Context, txs [][]byte) (string, error) {
	m.submittedCount.Add(1)

	if len(txs) == 0 {
		m.failedCount.Add(1)
		return "", errors.New("no transactions provided for bundle")
	}

	// Encode all transactions as base64
	txsBase64 := make([]string, len(txs))
	for i, tx := range txs {
		txsBase64[i] = base64.StdEncoding.EncodeToString(tx)
	}

	// Build bundle request
	bundleReq := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "sendBundle",
		"params": []interface{}{
			txsBase64,
			map[string]interface{}{
				"tipLamports": 10000, // default tip
			},
		},
	}

	bundleJSON, err := json.Marshal(bundleReq)
	if err != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("failed to marshal bundle request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, m.endpoint+jitoBundlesEndpoint, bytes.NewReader(bundleJSON))
	if err != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	httpResp, err := m.httpClient.Do(httpReq)
	if err != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("HTTP request failed: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK && httpResp.StatusCode != http.StatusAccepted {
		m.failedCount.Add(1)
		return "", fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	var resp jitoBundleResponse
	if err := json.NewDecoder(httpResp.Body).Decode(&resp); err != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	if resp.Error != nil {
		m.failedCount.Add(1)
		return "", fmt.Errorf("jito bundle error: %s (code %d)", resp.Error.Message, resp.Error.Code)
	}

	m.successCount.Add(1)
	return resp.Result.Signature, nil
}

// Stats returns the current submission statistics.
func (m *jitoMEV) Stats(ctx context.Context) (*JitoStats, error) {
	return &JitoStats{
		SubmittedCount: m.submittedCount.Load(),
		SuccessCount:   m.successCount.Load(),
		FailedCount:    m.failedCount.Load(),
	}, nil
}

// StatsSafe returns the current submission statistics without requiring context.
func (m *jitoMEV) StatsSafe() *JitoStats {
	return &JitoStats{
		SubmittedCount: m.submittedCount.Load(),
		SuccessCount:   m.successCount.Load(),
		FailedCount:    m.failedCount.Load(),
	}
}

// Type returns the type identifier for this MEV submitter.
func (m *jitoMEV) Type() string {
	return "jito"
}

// Compile-time interface assertion
var _ ports.MEVSubmitter = (*jitoMEV)(nil)