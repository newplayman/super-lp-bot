// Package rpc provides a round-robin RPC client with automatic failover.
package rpc

import (
	"context"
	"fmt"
	"math/big"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/ethclient"

	"github.com/lpbot/lpbot/internal/domain"
)

// Default public RPC endpoints
var (
	// Base mainnet endpoints
	BaseEndpoints = []string{
		"https://mainnet.base.org",
		"https://mainnet-preconf.base.org",
	}

	// Base Sepolia testnet endpoints
	BaseSepoliaEndpoints = []string{
		"https://sepolia.base.org",
		"https://sepolia-preconf.base.org",
	}

	// Ethereum mainnet endpoints
	EthEndpoints = []string{
		"https://eth.llamarpc.com",
		"https://rpc.ankr.com/eth",
	}

	// Solana mainnet endpoints
	SolanaEndpoints = []string{
		"https://api.mainnet.solana.com",
	}
)

// RoundRobinProvider distributes requests across multiple RPC endpoints with automatic failover.
type RoundRobinProvider struct {
	chainID   domain.ChainID
	client    *ethclient.Client
	mu        sync.RWMutex
	endpoints []string
	current   uint32 // atomic index
	httpClient *http.Client
}

// Config holds the configuration for a round-robin RPC provider.
type Config struct {
	ChainID    domain.ChainID
	Endpoints  []string
	HTTPClient *http.Client
}

// NewRoundRobinProvider creates a new round-robin RPC provider.
func NewRoundRobinProvider(cfg Config) (*RoundRobinProvider, error) {
	if len(cfg.Endpoints) == 0 {
		return nil, fmt.Errorf("at least one RPC endpoint is required")
	}

	p := &RoundRobinProvider{
		chainID:    cfg.ChainID,
		endpoints:  cfg.Endpoints,
		httpClient: cfg.HTTPClient,
	}

	// Use the first endpoint initially
	client, err := ethclient.Dial(cfg.Endpoints[0])
	if err != nil {
		return nil, fmt.Errorf("failed to connect to RPC endpoint: %w", err)
	}
	p.client = client

	return p, nil
}

// NewBaseProvider creates a provider for Base mainnet with default endpoints.
func NewBaseProvider() (*RoundRobinProvider, error) {
	return NewRoundRobinProvider(Config{
		ChainID:   domain.ChainBase,
		Endpoints: BaseEndpoints,
	})
}

// NewBaseSepoliaProvider creates a provider for Base Sepolia testnet.
func NewBaseSepoliaProvider() (*RoundRobinProvider, error) {
	return NewRoundRobinProvider(Config{
		ChainID:   "base-sepolia",
		Endpoints: BaseSepoliaEndpoints,
	})
}

// ChainID returns the chain ID.
func (p *RoundRobinProvider) ChainID() domain.ChainID {
	return p.chainID
}

// Client returns the current ethclient.
func (p *RoundRobinProvider) Client() *ethclient.Client {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.client
}

// Endpoint returns the current endpoint URL.
func (p *RoundRobinProvider) Endpoint() string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	idx := atomic.LoadUint32(&p.current) % uint32(len(p.endpoints))
	return p.endpoints[idx]
}

// nextEndpoint rotates to the next endpoint in the list.
func (p *RoundRobinProvider) nextEndpoint() error {
	idx := atomic.AddUint32(&p.current, 1) % uint32(len(p.endpoints))
	endpoint := p.endpoints[idx]

	client, err := ethclient.Dial(endpoint)
	if err != nil {
		return fmt.Errorf("failed to connect to endpoint %s: %w", endpoint, err)
	}

	p.mu.Lock()
	p.client = client
	p.mu.Unlock()

	return nil
}

// getClientWithRetry gets a client, rotating on failure.
func (p *RoundRobinProvider) getClientWithRetry() (*ethclient.Client, error) {
	p.mu.RLock()
	client := p.client
	p.mu.RUnlock()

	if client != nil {
		return client, nil
	}

	if err := p.nextEndpoint(); err != nil {
		return nil, err
	}

	p.mu.RLock()
	client = p.client
	p.mu.RUnlock()
	return client, nil
}

// BalanceAt returns the balance at the given block.
func (p *RoundRobinProvider) BalanceAt(ctx context.Context, addr domain.Address, block *big.Int) (*big.Int, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	balance, err := client.BalanceAt(ctx, common.HexToAddress(addr.String()), block)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.BalanceAt(ctx, addr, block)
		}
		return nil, err
	}
	return balance, nil
}

// NonceAt returns the nonce at the given block.
func (p *RoundRobinProvider) NonceAt(ctx context.Context, addr domain.Address, block *big.Int) (uint64, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return 0, err
	}

	nonce, err := client.NonceAt(ctx, common.HexToAddress(addr.String()), block)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.NonceAt(ctx, addr, block)
		}
		return 0, err
	}
	return nonce, nil
}

// PendingNonceAt returns the pending nonce for the given address.
// This is a convenience method for the RPCProvider interface.
func (p *RoundRobinProvider) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	// nil block means pending
	return p.NonceAt(ctx, addr, nil)
}
// BlockByHash returns the block with the given hash.
func (p *RoundRobinProvider) BlockByHash(ctx context.Context, hash common.Hash) (*types.Block, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	block, err := client.BlockByHash(ctx, hash)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.BlockByHash(ctx, hash)
		}
		return nil, err
	}
	return block, nil
}

// BlockByNumber returns the block with the given number.
func (p *RoundRobinProvider) BlockByNumber(ctx context.Context, num *big.Int) (*types.Block, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	block, err := client.BlockByNumber(ctx, num)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.BlockByNumber(ctx, num)
		}
		return nil, err
	}
	return block, nil
}

// HeaderByHash returns the header with the given hash.
func (p *RoundRobinProvider) HeaderByHash(ctx context.Context, hash common.Hash) (*types.Header, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	header, err := client.HeaderByHash(ctx, hash)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.HeaderByHash(ctx, hash)
		}
		return nil, err
	}
	return header, nil
}

// HeaderByNumber returns the header with the given number.
func (p *RoundRobinProvider) HeaderByNumber(ctx context.Context, num *big.Int) (*types.Header, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	header, err := client.HeaderByNumber(ctx, num)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.HeaderByNumber(ctx, num)
		}
		return nil, err
	}
	return header, nil
}

// SuggestGasPrice suggests a gas price based on the current network conditions.
func (p *RoundRobinProvider) SuggestGasPrice(ctx context.Context) (*big.Int, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	price, err := client.SuggestGasPrice(ctx)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.SuggestGasPrice(ctx)
		}
		return nil, err
	}
	return price, nil
}

// SuggestGasTipCap suggests a gas tip cap based on the current network conditions.
func (p *RoundRobinProvider) SuggestGasTipCap(ctx context.Context) (*big.Int, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	tip, err := client.SuggestGasTipCap(ctx)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.SuggestGasTipCap(ctx)
		}
		return nil, err
	}
	return tip, nil
}

// EstimateGas estimates the gas needed for a transaction.
func (p *RoundRobinProvider) EstimateGas(ctx context.Context, msg ethereum.CallMsg) (uint64, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return 0, err
	}

	gas, err := client.EstimateGas(ctx, msg)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.EstimateGas(ctx, msg)
		}
		return 0, err
	}
	return gas, nil
}

// CodeAt returns the code at the given address.
func (p *RoundRobinProvider) CodeAt(ctx context.Context, addr domain.Address, block *big.Int) ([]byte, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	code, err := client.CodeAt(ctx, common.HexToAddress(addr.String()), block)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.CodeAt(ctx, addr, block)
		}
		return nil, err
	}
	return code, nil
}

// PendingCodeAt returns the pending code at the given address.
func (p *RoundRobinProvider) PendingCodeAt(ctx context.Context, addr domain.Address) ([]byte, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	code, err := client.PendingCodeAt(ctx, common.HexToAddress(addr.String()))
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.PendingCodeAt(ctx, addr)
		}
		return nil, err
	}
	return code, nil
}

// CallContract executes a message call.
func (p *RoundRobinProvider) CallContract(ctx context.Context, msg ethereum.CallMsg, blockNumber *big.Int) ([]byte, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	result, err := client.CallContract(ctx, msg, blockNumber)
	if err != nil {
		if p.nextEndpoint() == nil {
			return p.CallContract(ctx, msg, blockNumber)
		}
		return nil, err
	}
	return result, nil
}

// FilterLogs executes a log filter query.
func (p *RoundRobinProvider) FilterLogs(ctx context.Context, q ethereum.FilterQuery) ([]types.Log, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	logs, err := client.FilterLogs(ctx, q)
	if err != nil {
		if p.nextEndpoint() != nil {
			return p.FilterLogs(ctx, q)
		}
		return nil, err
	}
	return logs, nil
}

// SendTransaction sends a signed transaction.
func (p *RoundRobinProvider) SendTransaction(ctx context.Context, tx *types.Transaction) error {
	client, err := p.getClientWithRetry()
	if err != nil {
		return err
	}

	err = client.SendTransaction(ctx, tx)
	if err != nil {
		if strings.Contains(err.Error(), "already known") || strings.Contains(err.Error(), "replacement underpriced") {
			return err // Don't retry for these errors
		}
		if p.nextEndpoint() == nil {
			return err
		}
		return p.SendTransaction(ctx, tx)
	}
	return nil
}

// TransactionByHash returns the transaction with the given hash.
func (p *RoundRobinProvider) TransactionByHash(ctx context.Context, hash common.Hash) (*types.Transaction, bool, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, false, err
	}

	tx, pending, err := client.TransactionByHash(ctx, hash)
	if err != nil {
		if p.nextEndpoint() == nil {
			return nil, false, err
		}
		return p.TransactionByHash(ctx, hash)
	}
	return tx, pending, nil
}

// TransactionReceipt returns the receipt for the given transaction hash.
func (p *RoundRobinProvider) TransactionReceipt(ctx context.Context, hash common.Hash) (*types.Receipt, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	receipt, err := client.TransactionReceipt(ctx, hash)
	if err != nil {
		if p.nextEndpoint() == nil {
			return nil, err
		}
		return p.TransactionReceipt(ctx, hash)
	}
	return receipt, nil
}

// NetworkID returns the network ID.
func (p *RoundRobinProvider) NetworkID(ctx context.Context) (*big.Int, error) {
	client, err := p.getClientWithRetry()
	if err != nil {
		return nil, err
	}

	id, err := client.NetworkID(ctx)
	if err != nil {
		if p.nextEndpoint() == nil {
			return nil, err
		}
		return nil, err
	}
	return id, nil
}