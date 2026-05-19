// Package solana provides the Solana chain adapter implementation.
package solana

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Adapter implements ports.SolanaChain for Solana blockchain.
// This is a stub implementation - see T-091 for Phase 1 details.
type Adapter struct{}

func (*Adapter) Info() ports.ChainInfo {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) LatestBlockhash(ctx context.Context) (string, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

func (*Adapter) GetComputeUnitPrice(ctx context.Context) (uint64, error) {
	panic("not implemented: T-091 solana adapter (Phase 1)")
}

// Compile-time interface assertion
var _ ports.SolanaChain = (*Adapter)(nil)