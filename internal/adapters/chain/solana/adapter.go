// Package solana provides the Solana chain adapter implementation.
package solana

import (
	"context"
	"errors"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

var ErrNotImplemented = errors.New("solana chain adapter is not implemented")

// Adapter implements ports.SolanaChain for Solana blockchain.
// This is a stub implementation - see T-091 for Phase 1 details.
type Adapter struct{}

func (*Adapter) Info() ports.ChainInfo {
	return ports.ChainInfo{
		ID:            domain.ChainSolana,
		Name:          "Solana",
		NativeSymbol:  "SOL",
		Confirmations: 1,
	}
}

func (*Adapter) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, ErrNotImplemented
}

func (*Adapter) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	return nil, ErrNotImplemented
}

func (*Adapter) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	return nil, ErrNotImplemented
}

func (*Adapter) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, ErrNotImplemented
}

func (*Adapter) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	return nil, ErrNotImplemented
}

func (*Adapter) LatestBlockhash(ctx context.Context) (string, error) {
	return "", ErrNotImplemented
}

func (*Adapter) GetComputeUnitPrice(ctx context.Context) (uint64, error) {
	return 0, ErrNotImplemented
}

// Compile-time interface assertion
var _ ports.SolanaChain = (*Adapter)(nil)
