// Package mocks provides mock implementations for ports interfaces.
package mocks

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// MockChain is a mock implementation of ports.Chain for testing.
type MockChain struct {
	InfoFunc          func() ports.ChainInfo
	GetBlockFunc      func(ctx context.Context, ref domain.BlockRef) (ports.Block, error)
	SubscribeBlocksFunc func(ctx context.Context) (<-chan ports.Block, error)
	MulticallFunc     func(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error)
	EstimateGasFunc   func(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error)
	ListMyPositionsFunc func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error)
}

func (m *MockChain) Info() ports.ChainInfo {
	if m.InfoFunc != nil {
		return m.InfoFunc()
	}
	return ports.ChainInfo{}
}

func (m *MockChain) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	if m.GetBlockFunc != nil {
		return m.GetBlockFunc(ctx, ref)
	}
	return ports.Block{}, nil
}

func (m *MockChain) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	if m.SubscribeBlocksFunc != nil {
		return m.SubscribeBlocksFunc(ctx)
	}
	return nil, nil
}

func (m *MockChain) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	if m.MulticallFunc != nil {
		return m.MulticallFunc(ctx, calls)
	}
	return nil, nil
}

func (m *MockChain) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	if m.EstimateGasFunc != nil {
		return m.EstimateGasFunc(ctx, tx)
	}
	return ports.GasEstimate{}, nil
}

func (m *MockChain) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	if m.ListMyPositionsFunc != nil {
		return m.ListMyPositionsFunc(ctx, owner)
	}
	return nil, nil
}

// MockEVMChain is a mock implementation of ports.EVMChain for testing.
type MockEVMChain struct {
	MockChain

	NonceAtFunc        func(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error)
	PendingNonceAtFunc func(ctx context.Context, addr domain.Address) (uint64, error)
	SuggestGasFeesFunc func(ctx context.Context) (baseFee, tip *big.Int, err error)
}

func (m *MockEVMChain) NonceAt(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error) {
	if m.NonceAtFunc != nil {
		return m.NonceAtFunc(ctx, addr, ref)
	}
	return 0, nil
}

func (m *MockEVMChain) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	if m.PendingNonceAtFunc != nil {
		return m.PendingNonceAtFunc(ctx, addr)
	}
	return 0, nil
}

func (m *MockEVMChain) SuggestGasFees(ctx context.Context) (baseFee, tip *big.Int, err error) {
	if m.SuggestGasFeesFunc != nil {
		return m.SuggestGasFeesFunc(ctx)
	}
	return nil, nil, nil
}

// MockSolanaChain is a mock implementation of ports.SolanaChain for testing.
type MockSolanaChain struct {
	MockChain

	LatestBlockhashFunc    func(ctx context.Context) (string, error)
	GetComputeUnitPriceFunc func(ctx context.Context) (uint64, error)
}

func (m *MockSolanaChain) LatestBlockhash(ctx context.Context) (string, error) {
	if m.LatestBlockhashFunc != nil {
		return m.LatestBlockhashFunc(ctx)
	}
	return "", nil
}

func (m *MockSolanaChain) GetComputeUnitPrice(ctx context.Context) (uint64, error) {
	if m.GetComputeUnitPriceFunc != nil {
		return m.GetComputeUnitPriceFunc(ctx)
	}
	return 0, nil
}