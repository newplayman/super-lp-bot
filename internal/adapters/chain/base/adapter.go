// Package base provides the EVM chain adapter implementation.
package base

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Adapter implements ports.EVMChain for EVM-compatible chains (Base, Ethereum, etc.).
// This is a stub implementation - see T-090 for Phase 1 details.
type Adapter struct{}

func (*Adapter) Info() ports.ChainInfo {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) NonceAt(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

func (*Adapter) SuggestGasFees(ctx context.Context) (baseFee, tip *big.Int, err error) {
	panic("not implemented: T-090 base adapter (Phase 1)")
}

// Compile-time interface assertion
var _ ports.EVMChain = (*Adapter)(nil)