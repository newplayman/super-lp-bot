// Package ports defines the interfaces for external dependencies.
// Ports follow the hexagonal architecture pattern, allowing the core
// business logic to remain independent of specific implementations.
package ports

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
)

// ChainInfo holds metadata about a blockchain network.
type ChainInfo struct {
	// ID is the unique identifier for the chain (e.g., "base", "solana").
	ID domain.ChainID
	// Name is the human-readable name of the chain (e.g., "Base", "Solana").
	Name string
	// NativeSymbol is the symbol of the chain's native token (e.g., "ETH", "SOL").
	NativeSymbol string
	// Confirmations is the number of block confirmations required for finality.
	Confirmations int
}

// Block represents a blockchain block.
type Block struct {
	// Ref is the block reference containing chain, number, hash, and timestamp.
	Ref domain.BlockRef
	// Timestamp is the Unix timestamp of the block.
	Timestamp int64
}

// Call represents a read-only call to a contract or account.
type Call struct {
	// Target is the address to call.
	Target domain.Address
	// Data is the calldata payload.
	Data []byte
}

// CallResult holds the result of a contract call.
type CallResult struct {
	// Success indicates whether the call succeeded.
	Success bool
	// Data is the return data from the call.
	Data []byte
}

// GasEstimate contains gas cost information for a transaction.
type GasEstimate struct {
	// UnitsUsed is the amount of gas units consumed.
	UnitsUsed uint64
	// UnitCost is the cost per gas unit (in wei or lamports).
	UnitCost *big.Int
	// TotalCost is the total transaction cost (UnitsUsed * UnitCost).
	TotalCost *big.Int
}

// ChainPosition represents a position on a specific chain.
type ChainPosition struct {
	// PoolID is the identifier of the pool this position belongs to.
	PoolID string
	// OnChain is the chain-specific payload (e.g., NFT token ID for EVM,
	// associated token account for Solana).
	OnChain []byte
}

// UnsignedTx represents an unsigned transaction that needs to be signed.
type UnsignedTx struct {
	// Chain is the target chain for the transaction.
	Chain domain.ChainID
	// Payload is the chain-specific serialized transaction data.
	Payload []byte
	// Meta contains additional metadata for the transaction.
	Meta map[string]string
}

// Chain defines the interface for interacting with any blockchain.
// Implementations must be safe for concurrent use.
type Chain interface {
	// Info returns metadata about the chain.
	Info() ChainInfo
	// GetBlock retrieves a block by its reference.
	GetBlock(ctx context.Context, ref domain.BlockRef) (Block, error)
	// SubscribeBlocks returns a channel that receives new blocks as they are produced.
	SubscribeBlocks(ctx context.Context) (<-chan Block, error)
	// Multicall executes multiple calls in a single batch request.
	Multicall(ctx context.Context, calls []Call) ([]CallResult, error)
	// EstimateGas estimates the gas cost for an unsigned transaction.
	EstimateGas(ctx context.Context, tx UnsignedTx) (GasEstimate, error)
	// ListMyPositions returns all positions owned by the given address.
	ListMyPositions(ctx context.Context, owner domain.Address) ([]ChainPosition, error)
}

// EVMChain defines the interface for EVM-compatible chains (e.g., Base, Ethereum).
// It extends the base Chain interface with EVM-specific operations.
type EVMChain interface {
	Chain
	// NonceAt returns the nonce of an account at a specific block reference.
	NonceAt(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error)
	// PendingNonceAt returns the pending nonce of an account (for next transaction).
	PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error)
	// SuggestGasFees returns the suggested base fee and priority tip for gas pricing.
	SuggestGasFees(ctx context.Context) (baseFee, tip *big.Int, err error)
}

// SolanaChain defines the interface for Solana blockchain.
// It extends the base Chain interface with Solana-specific operations.
type SolanaChain interface {
	Chain
	// LatestBlockhash returns the latest finalized blockhash.
	LatestBlockhash(ctx context.Context) (string, error)
	// GetComputeUnitPrice returns the recommended compute unit price in microlamports.
	GetComputeUnitPrice(ctx context.Context) (uint64, error)
}