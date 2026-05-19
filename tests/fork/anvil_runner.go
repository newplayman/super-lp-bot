// Package fork provides testing utilities for forked blockchain environments.
package fork

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"testing"
	"time"
)

// AnvilRunner manages an anvil EVM node for fork testing.
type AnvilRunner struct {
	cmd    *exec.Cmd
	rpcURL string
	t      *testing.T
	pid    int
}

// StartAnvil starts an anvil node forked at the given URL and block number.
// It skips the test if -short flag is set or if anvil is not installed.
func StartAnvil(t *testing.T, forkURL string, blockNumber uint64) *AnvilRunner {
	if testing.Short() {
		t.Skip("fork test skipped in short mode")
	}

	// Check if anvil is available
	if _, err := exec.LookPath("anvil"); err != nil {
		t.Skip("anvil not found in PATH")
	}

	rpcPort := pickFreePort()
	rpcURL := fmt.Sprintf("http://127.0.0.1:%d", rpcPort)

	args := []string{
		"--fork-url", forkURL,
		"--fork-block-number", fmt.Sprintf("%d", blockNumber),
		"--port", fmt.Sprintf("%d", rpcPort),
		"--host", "127.0.0.1",
		"--steps-tracing",
		"--silent",
	}

	cmd := exec.Command("anvil", args...)
	cmd.Stdout = nil
	cmd.Stderr = nil

	if err := cmd.Start(); err != nil {
		t.Fatalf("failed to start anvil: %v", err)
	}

	runner := &AnvilRunner{
		cmd:    cmd,
		rpcURL: rpcURL,
		t:      t,
		pid:    cmd.Process.Pid,
	}

	// Wait for anvil to be ready
	if !runner.waitForRPC(10 * time.Second) {
		_ = cmd.Process.Kill()
		t.Fatalf("anvil failed to start within timeout")
	}

	t.Cleanup(runner.Stop)
	return runner
}

// RPC returns the HTTP RPC URL for the anvil instance.
func (a *AnvilRunner) RPC() string {
	return a.rpcURL
}

// Stop terminates the anvil process.
func (a *AnvilRunner) Stop() {
	if a.cmd != nil && a.cmd.Process != nil {
		_ = a.cmd.Process.Kill()
		_ = a.cmd.Wait()
	}
}

// waitForRPC polls the RPC endpoint until it's ready or timeout.
func (a *AnvilRunner) waitForRPC(timeout time.Duration) bool {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return false
		case <-ticker.C:
			resp, err := http.Get(a.rpcURL)
			if err != nil {
				continue
			}
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return true
			}
		}
	}
}

// EthClient provides a simple JSON-RPC client for anvil.
type EthClient struct {
	rpcURL string
	client *http.Client
}

// NewEthClient creates a client for the given RPC URL.
func NewEthClient(rpcURL string) *EthClient {
	return &EthClient{
		rpcURL: rpcURL,
		client: &http.Client{Timeout: 30 * time.Second},
	}
}

// ChainID returns the chain ID of the connected node.
func (c *EthClient) ChainID(ctx context.Context) (string, error) {
	var result string
	err := c.call(ctx, "eth_chainId", nil, &result)
	return result, err
}

// BlockNumber returns the current block number.
func (c *EthClient) BlockNumber(ctx context.Context) (uint64, error) {
	var result string
	err := c.call(ctx, "eth_blockNumber", nil, &result)
	if err != nil {
		return 0, err
	}
	return parseHexUint64(result)
}

// Call executes a smart contract call.
func (c *EthClient) Call(ctx context.Context, method string, params []interface{}) (json.RawMessage, error) {
	var result json.RawMessage
	err := c.call(ctx, method, params, &result)
	return result, err
}

func (c *EthClient) call(ctx context.Context, method string, params, result interface{}) error {
	reqBody, err := json.Marshal(map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  method,
		"params":  params,
		"id":      1,
	})
	if err != nil {
		return fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.rpcURL, bytes.NewReader(reqBody))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("rpc call: %w", err)
	}
	defer resp.Body.Close()

	var rpcResp struct {
		JSONRPC string          `json:"jsonrpc"`
		ID     int             `json:"id"`
		Result json.RawMessage `json:"result"`
		Error  *struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&rpcResp); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	if rpcResp.Error != nil {
		return fmt.Errorf("rpc error %d: %s", rpcResp.Error.Code, rpcResp.Error.Message)
	}

	data, _ := json.Marshal(rpcResp.Result)
	json.Unmarshal(data, result)
	return nil
}

func parseHexUint64(s string) (uint64, error) {
	var v uint64
	_, err := fmt.Sscanf(s, "0x%x", &v)
	return v, err
}

// pickFreePort finds an available port on localhost.
func pickFreePort() int {
	l, err := os.CreateTemp("", "anvil-port")
	if err != nil {
		return 8545 + int(time.Now().UnixNano()%1000)
	}
	portStr := l.Name()
	l.Close()
	os.Remove(portStr)
	// Use a listener to get a free port
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 8545
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port
}