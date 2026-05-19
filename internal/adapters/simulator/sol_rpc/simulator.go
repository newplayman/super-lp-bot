// Package sol_rpc provides a Solana RPC-based transaction simulator implementation.
package sol_rpc

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/gagliardetto/solana-go"
	"github.com/gagliardetto/solana-go/programs/system"
	"github.com/gagliardetto/solana-go/rpc/jsonrpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// DefaultRPCEndpoint is the default Solana RPC endpoint.
const DefaultRPCEndpoint = "https://api.mainnet-beta.solana.com"

// simulator is a Solana RPC simulator implementation.
type simulator struct {
	rpcEndpoint string
	httpClient  *http.Client
}

// Config holds Solana RPC simulator configuration.
type Config struct {
	// RPCEndpoint is the Solana RPC URL. Default is Mainnet Beta.
	RPCEndpoint string
}

// New creates a new Solana RPC simulator.
func New(cfg Config) *simulator {
	endpoint := cfg.RPCEndpoint
	if endpoint == "" {
		endpoint = DefaultRPCEndpoint
	}

	return &simulator{
		rpcEndpoint: endpoint,
		httpClient:  &http.Client{Timeout: 30 * time.Second},
	}
}

// toContext converts an any (interface{}) to context.Context.
func toContext(ctx any) context.Context {
	if c, ok := ctx.(context.Context); ok {
		return c
	}
	return context.Background()
}

// Simulate implements ports.Simulator.
// Uses Solana's simulateTransaction RPC method to simulate the transaction.
func (s *simulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	c := toContext(ctx)

	// Convert domain tx to Solana transaction
	solTx, err := s.toSolanaTx(tx)
	if err != nil {
		return &domain.SimulationResult{
			Success:  false,
			Error:    fmt.Sprintf("failed to convert transaction: %v", err),
			BlockRef: blockRef,
		}, nil
	}

	// Encode transaction as base64
	txBytes, err := solTx.MarshalBinary()
	if err != nil {
		return &domain.SimulationResult{
			Success:  false,
			Error:    fmt.Sprintf("failed to marshal transaction: %v", err),
			BlockRef: blockRef,
		}, nil
	}
	txBase64 := base64.StdEncoding.EncodeToString(txBytes)

	// Build simulation request
	result, err := s.simulateTransaction(c, txBase64, blockRef)
	if err != nil {
		return &domain.SimulationResult{
			Success:  false,
			Error:    fmt.Sprintf("simulation failed: %v", err),
			BlockRef: blockRef,
		}, nil
	}

	return result, nil
}

// SimulateSequence implements ports.Simulator.
func (s *simulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	c := toContext(ctx)

	results := make([]domain.SimulationResult, len(txs))
	for i, tx := range txs {
		result, err := s.Simulate(c, tx, blockRef)
		if err != nil {
			results[i] = domain.SimulationResult{
				Success:  false,
				Error:    err.Error(),
				BlockRef: blockRef,
			}
			continue
		}
		results[i] = *result
	}

	return results, nil
}

// toSolanaTx converts a domain.UnsignedTx to a solana-go Transaction.
func (s *simulator) toSolanaTx(tx domain.UnsignedTx) (*solana.Transaction, error) {
	// Parse the from address
	var from solana.PublicKey
	if !tx.From.IsZero() {
		fromBytes := tx.From.Bytes()
		if len(fromBytes) == 32 {
			copy(from[:], fromBytes)
		}
	}

	// Parse the to address
	var to solana.PublicKey
	if !tx.To.IsZero() {
		toBytes := tx.To.Bytes()
		if len(toBytes) == 32 {
			copy(to[:], toBytes)
		}
	}

	// Build the transaction
	recentBlockhash := solana.Hash{} // Placeholder; will be filled by simulateTransaction
	txBuilder := solana.NewTransactionBuilder()

	// Add the transfer instruction if data is empty (simple SOL transfer)
	if len(tx.Data) == 0 && to != (solana.PublicKey{}) {
		// Simple transfer instruction
		amount := uint64(0)
		if !tx.Value.IsZero() {
			// Convert decimal to uint64 (lamports are whole numbers)
			amount = tx.Value.BigInt().Uint64()
			if amount == 0 && tx.Value.IsPositive() {
				amount = 1 // minimum 1 lamport
			}
		}

		transferInstruction := system.NewTransferInstruction(
			amount,
			from,
			to,
		).Build()
		txBuilder.AddInstruction(transferInstruction)
	} else if len(tx.Data) > 0 {
		// For more complex transactions, add custom instruction data
		// Use system program as placeholder program ID
		instruction := solana.NewInstruction(
			system.ProgramID,
			[]*solana.AccountMeta{
				solana.NewAccountMeta(from, true, true),
				solana.NewAccountMeta(to, false, true),
			},
			tx.Data,
		)
		txBuilder.AddInstruction(instruction)
	}

	// Set fee payer
	txBuilder.SetFeePayer(from)

	// Set recent blockhash (placeholder)
	txBuilder.SetRecentBlockHash(recentBlockhash)

	return txBuilder.Build()
}

// simulateTransaction calls the Solana JSON-RPC simulateTransaction endpoint.
func (s *simulator) simulateTransaction(ctx context.Context, txBase64 string, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	// Build the JSON-RPC request
	params := []interface{}{
		txBase64,
		map[string]interface{}{
			"encoding":                       "base64",
			"replaceRecentBlockhash":         true,
			"commitment":                     "processed",
			"sigVerify":                      false,
			"ignoreUnexpectedSignatures":     false,
		},
	}

	// Add minContextSlot if specified
	if blockRef.Number > 0 {
		params[1] = map[string]interface{}{
			"encoding":                       "base64",
			"replaceRecentBlockhash":         true,
			"commitment":                     "processed",
			"sigVerify":                      false,
			"ignoreUnexpectedSignatures":     false,
			"minContextSlot":                 blockRef.Number,
		}
	}

	payload := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "simulateTransaction",
		"params":  params,
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// Create HTTP request
	req, err := http.NewRequestWithContext(ctx, "POST", s.rpcEndpoint, bytes.NewReader(payloadBytes))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	// Execute request
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	// Parse response
	var rpcResp simulateTransactionResponse
	if err := json.NewDecoder(resp.Body).Decode(&rpcResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	// Build simulation result
	result := &domain.SimulationResult{
		BlockRef: blockRef,
	}

	// Check for RPC error
	if rpcResp.Error != nil {
		result.Success = false
		result.Error = fmt.Sprintf("RPC error: %s", rpcResp.Error.Message)
		return result, nil
	}

	// Parse simulation result - handle both direct result and wrapped result formats
	var simErr interface{}
	var logs []string
	var unitsConsumed uint64

	if rpcResp.Result != nil {
		// Try nested format first (result.value)
		if rpcResp.Result.Value != nil {
			logs = rpcResp.Result.Value.Logs
			simErr = rpcResp.Result.Value.Err
			unitsConsumed = rpcResp.Result.Value.UnitsConsumed
		} else {
			// Try direct format (result.logs)
			logs = rpcResp.Result.Logs
			simErr = rpcResp.Result.Err
			unitsConsumed = rpcResp.Result.UnitsConsumed
		}

		// Check simulation logs
		if len(logs) > 0 {
			result.ReturnData = []byte{}
			for _, log := range logs {
				result.ReturnData = append(result.ReturnData, []byte(log+"\n")...)
			}
		}

		// Check for simulation error
		if simErr != nil {
			errStr := formatSolanaError(simErr)
			result.Success = false
			result.Error = errStr
			return result, nil
		}

		// Simulation succeeded
		result.Success = true

		// Parse units consumed
		if unitsConsumed > 0 {
			result.GasUsed = unitsConsumed
		}
	}

	return result, nil
}

// simulateTransactionResponse represents the Solana simulateTransaction RPC response.
type simulateTransactionResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID     int             `json:"id"`
	Result *simResultValue `json:"result,omitempty"`
	Error  *jsonrpc.RPCError `json:"error,omitempty"`
}

// simResultValue represents the result field in simulateTransaction response.
type simResultValue struct {
	// Nested format: result.value.{logs,err,unitsConsumed}
	Value *simValue `json:"value,omitempty"`
	// Direct format: result.{logs,err,unitsConsumed}
	Logs          []string     `json:"logs,omitempty"`
	Err           interface{}  `json:"err,omitempty"`
	UnitsConsumed uint64       `json:"unitsConsumed,omitempty"`
	ReturnData    *simReturnData `json:"returnData,omitempty"`
}

// simValue represents the value field in simulateTransaction response.
type simValue struct {
	Logs          []string       `json:"logs,omitempty"`
	Err           interface{}    `json:"err,omitempty"`
	UnitsConsumed uint64         `json:"unitsConsumed,omitempty"`
	ReturnData    *simReturnData `json:"returnData,omitempty"`
}

// simReturnData represents the returnData field in simulation result.
type simReturnData struct {
	ProgramID string `json:"programId"`
	Data      string `json:"data"`
}

// formatSolanaError converts Solana error object to string.
func formatSolanaError(err interface{}) string {
	if err == nil {
		return ""
	}

	switch v := err.(type) {
	case string:
		return v
	case map[string]interface{}:
		// Solana error can be an object like {"InstructionError": [0, "InsufficientFunds"]}
		for k, val := range v {
			return fmt.Sprintf("%s: %v", k, val)
		}
	}

	return fmt.Sprintf("%v", err)
}

// Compile-time interface assertion
var _ ports.Simulator = (*simulator)(nil)