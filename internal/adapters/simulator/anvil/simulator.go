// Package anvil provides an Anvil-based transaction simulator implementation.
package anvil

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// DefaultAnvilPort is the default port for Anvil JSON-RPC server.
const DefaultAnvilPort = 8545

// AnvilPath returns the path to the anvil binary.
// Returns empty string if not found in PATH.
func AnvilPath() string {
	path, err := exec.LookPath("anvil")
	if err != nil {
		return ""
	}
	return path
}

// simulator is an Anvil simulator implementation.
type simulator struct {
	anvilPath   string
	port        int
	forkURL     string
	httpClient  *http.Client
	rpcEndpoint string
}

// Config holds Anvil simulator configuration.
type Config struct {
	// AnvilPath is the path to the anvil binary. If empty, uses "anvil" from PATH.
	AnvilPath string
	// Port is the JSON-RPC server port. Default is 8545.
	Port int
	// ForkURL is the RPC URL to fork from (e.g., Alchemy, Infura).
	// If empty, simulation will use local state (not forked).
	ForkURL string
}

// New creates a new Anvil simulator with the given configuration.
func New(cfg Config) *simulator {
	anvilPath := cfg.AnvilPath
	if anvilPath == "" {
		anvilPath = "anvil"
	}

	port := cfg.Port
	if port == 0 {
		port = DefaultAnvilPort
	}

	return &simulator{
		anvilPath:   anvilPath,
		port:        port,
		forkURL:     cfg.ForkURL,
		httpClient:  &http.Client{Timeout: 30 * time.Second},
		rpcEndpoint: fmt.Sprintf("http://127.0.0.1:%d", port),
	}
}

// toContext converts an any (interface{}) to context.Context.
// Returns context.Background() if the conversion fails.
func toContext(ctx any) context.Context {
	if c, ok := ctx.(context.Context); ok {
		return c
	}
	return context.Background()
}

// Simulate implements ports.Simulator by forking from blockRef and executing eth_call.
func (s *simulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	c := toContext(ctx)

	// Start Anvil with fork configuration
	anvil, err := s.startAnvil(blockRef)
	if err != nil {
		return nil, fmt.Errorf("failed to start anvil: %w", err)
	}
	defer anvil.Stop()

	// Wait for anvil to be ready
	if err := s.waitForReady(c); err != nil {
		return nil, fmt.Errorf("anvil not ready: %w", err)
	}

	// Execute eth_call
	result, err := s.ethCall(c, tx)
	if err != nil {
		return &domain.SimulationResult{
			Success:  false,
			Error:    err.Error(),
			BlockRef: blockRef,
		}, nil
	}

	return result, nil
}

// SimulateSequence implements ports.Simulator.
func (s *simulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	c := toContext(ctx)

	// Start Anvil with fork configuration
	anvil, err := s.startAnvil(blockRef)
	if err != nil {
		return nil, fmt.Errorf("failed to start anvil: %w", err)
	}
	defer anvil.Stop()

	// Wait for anvil to be ready
	if err := s.waitForReady(c); err != nil {
		return nil, fmt.Errorf("anvil not ready: %w", err)
	}

	// Execute eth_calls sequentially
	results := make([]domain.SimulationResult, len(txs))
	for i, tx := range txs {
		result, err := s.ethCall(c, tx)
		if err != nil {
			results[i] = domain.SimulationResult{
				Success:  false,
				Error:    err.Error(),
				BlockRef: blockRef,
			}
			// Continue with remaining transactions for partial results
			continue
		}
		results[i] = *result
	}

	return results, nil
}

// anvilProcess holds the Anvil process and its cleanup function.
type anvilProcess struct {
	cmd  *exec.Cmd
	done chan struct{}
}

// startAnvil starts an Anvil instance forked from the given block reference.
func (s *simulator) startAnvil(blockRef domain.BlockRef) (*anvilProcess, error) {
	args := []string{
		"--port", strconv.Itoa(s.port),
		"--host", "127.0.0.1",
		"--block-gas-limit", "30000000",
	}

	// Add fork URL if configured
	if s.forkURL != "" {
		args = append(args, "--fork-url", s.forkURL)
	} else if blockRef.Hash != "" || blockRef.Number > 0 {
		// Fork from specific block hash if RPC URL is configured
		// This requires an RPC URL to be set
		return nil, fmt.Errorf("fork-url is required for real simulation")
	}

	// Add fork block number if specified
	if blockRef.Number > 0 {
		args = append(args, "--fork-block-number", strconv.FormatUint(blockRef.Number, 10))
	}

	cmd := exec.Command(s.anvilPath, args...)
	cmd.Stdout = nil
	cmd.Stderr = nil

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start anvil: %w", err)
	}

	return &anvilProcess{
		cmd:  cmd,
		done: make(chan struct{}),
	}, nil
}

// Stop terminates the Anvil process.
func (p *anvilProcess) Stop() {
	if p.cmd.Process != nil {
		p.cmd.Process.Kill()
	}
	p.cmd.Wait()
	close(p.done)
}

// waitForReady waits for Anvil to be ready to accept RPC requests.
func (s *simulator) waitForReady(ctx context.Context) error {
	deadline, ok := ctx.Deadline()
	if !ok {
		deadline = time.Now().Add(30 * time.Second)
	}

	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	timeout := time.NewTimer(time.Until(deadline))
	defer timeout.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-timeout.C:
			return fmt.Errorf("timeout waiting for anvil to be ready")
		case <-ticker.C:
			conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", s.port), 100*time.Millisecond)
			if err == nil {
				conn.Close()
				return nil
			}
		}
	}
}

// ethCall executes a transaction simulation via eth_call JSON-RPC.
func (s *simulator) ethCall(ctx context.Context, tx domain.UnsignedTx) (*domain.SimulationResult, error) {
	// Build eth_call request
	callParams := map[string]interface{}{
		"from": tx.From.String(),
		"to":   tx.To.String(),
		"data": bytesToHex(tx.Data),
	}

	if tx.Value != domain.ZeroDecimal() {
		callParams["value"] = fmt.Sprintf("0x%x", tx.Value)
	}

	// Build request payload
	payload := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "eth_call",
		"params":  []interface{}{callParams, "latest"},
		"id":      1,
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// Execute request
	req, err := http.NewRequestWithContext(ctx, "POST", s.rpcEndpoint, strings.NewReader(string(payloadBytes)))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	// Parse response
	var rpcResp rpcResponse
	if err := json.NewDecoder(resp.Body).Decode(&rpcResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	result := &domain.SimulationResult{}

	if rpcResp.Error != nil {
		result.Success = false
		result.Error = rpcResp.Error.Message
		return result, nil
	}

	// rpcResp.Result is json.RawMessage, check if it's non-empty
	if len(rpcResp.Result) > 0 {
		result.Success = true
		result.ReturnData, err = hexToBytes(string(rpcResp.Result))
		if err != nil {
			return nil, fmt.Errorf("failed to decode return data: %w", err)
		}
	}

	// Get gas used from trace (if available) or estimate
	gasUsed, err := s.getGasUsed(ctx)
	if err == nil {
		result.GasUsed = gasUsed
	} else {
		result.GasUsed = 21000 // default gas for transfer
	}

	return result, nil
}

// rpcResponse represents a JSON-RPC response.
type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// getGasUsed estimates gas usage by running eth_estimateGas.
func (s *simulator) getGasUsed(ctx context.Context) (uint64, error) {
	payload := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "eth_estimateGas",
		"params":  []interface{}{map[string]string{}},
		"id":      1,
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return 0, err
	}

	req, err := http.NewRequestWithContext(ctx, "POST", s.rpcEndpoint, strings.NewReader(string(payloadBytes)))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	var rpcResp rpcResponse
	if err := json.NewDecoder(resp.Body).Decode(&rpcResp); err != nil {
		return 0, err
	}

	if rpcResp.Error != nil {
		return 0, fmt.Errorf("%s", rpcResp.Error.Message)
	}

	// Parse gas from hex string
	gasStr := strings.Trim(string(rpcResp.Result), `"`)
	gas, err := strconv.ParseUint(gasStr, 0, 64)
	if err != nil {
		return 0, err
	}

	return gas, nil
}

// bytesToHex converts byte slice to hex string with "0x" prefix.
func bytesToHex(data []byte) string {
	if len(data) == 0 {
		return "0x"
	}
	const hexChars = "0123456789abcdef"
	result := make([]byte, len(data)*2+2)
	result[0] = '0'
	result[1] = 'x'
	for i, b := range data {
		result[i*2+2] = hexChars[b>>4]
		result[i*2+3] = hexChars[b&0x0f]
	}
	return string(result)
}

// hexToBytes converts hex string to byte slice.
func hexToBytes(s string) ([]byte, error) {
	s = strings.TrimPrefix(s, "0x")
	if len(s)%2 != 0 {
		return nil, fmt.Errorf("hex string must have even length")
	}
	result := make([]byte, len(s)/2)
	for i := 0; i < len(s); i += 2 {
		b, err := strconv.ParseUint(s[i:i+2], 16, 8)
		if err != nil {
			return nil, err
		}
		result[i/2] = byte(b)
	}
	return result, nil
}

// parseAnvilLog reads the Anvil log output line by line.
func parseAnvilLog(r *bufio.Reader) (bool, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return false, err
	}
	// Anvil is ready when it prints the JSON-RPC endpoint info
	return strings.Contains(line, "Listening on") || strings.Contains(line, "http://127.0.0.1"), nil
}

// Compile-time interface assertion
var _ ports.Simulator = (*simulator)(nil)
