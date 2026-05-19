package fork

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// SolanaSimulator wraps the Solana RPC simulate endpoint for testing.
type SolanaSimulator struct {
	rpcURL string
	client *http.Client
}

// SimulateRequest represents a Solana simulate transaction request.
type SimulateRequest struct {
	Transaction string `json:"transaction"` // base58 or base64 encoded
	Config      struct {
		SigVerify   bool `json:"sigVerify"`
		ReplaceInc  bool `json:"replaceInc"`
		Accounts    *struct {
			Encoding string `json:"encoding"`
		} `json:"accounts"`
	} `json:"config"`
}

// SimulateResponse represents a Solana simulate transaction response.
type SimulateResponse struct {
	JSONRPC string `json:"jsonrpc"`
	ID     int     `json:"id"`
	Result struct {
		Logs     []string `json:"logs"`
		Accounts []struct {
			Executable bool     `json:"executable"`
			Owner      string   `json:"owner"`
			Lamports   int64    `json:"lamports"`
			Data      []string `json:"data"`
			RentEpoch int64    `json:"rentEpoch"`
		} `json:"accounts"`
		UnitsConsumed uint64      `json:"unitsConsumed"`
		Err          interface{} `json:"err"`
	} `json:"result"`
	Error *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

// NewSolanaSimulator creates a simulator for the given RPC URL.
func NewSolanaSimulator(rpcURL string) *SolanaSimulator {
	return &SolanaSimulator{
		rpcURL: rpcURL,
		client: &http.Client{Timeout: 60 * time.Second},
	}
}

// Simulate executes a simulated transaction.
// Returns logs and any error from simulation.
func (s *SolanaSimulator) Simulate(ctx context.Context, req SimulateRequest) (*SimulateResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", s.rpcURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := s.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("simulate: %w", err)
	}
	defer resp.Body.Close()

	var result SimulateResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	if result.Error != nil {
		return &result, fmt.Errorf("simulate error %d: %s", result.Error.Code, result.Error.Message)
	}

	return &result, nil
}

// SimulateSimple executes a simple simulated transaction with logs.
func (s *SolanaSimulator) SimulateSimple(ctx context.Context, transaction string) ([]string, error) {
	req := SimulateRequest{
		Transaction: transaction,
	}
	req.Config.SigVerify = false
	req.Config.ReplaceInc = true

	result, err := s.Simulate(ctx, req)
	if err != nil {
		return nil, err
	}

	return result.Result.Logs, nil
}