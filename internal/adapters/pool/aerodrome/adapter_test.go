package aerodrome

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

// Test helper to create adapter with mock chain
func newTestAdapter() *Adapter {
	return &Adapter{
		poolID:   "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
		chain:    domain.ChainBase,
		protocol: "aerodrome",
		token0:   domain.MustParseAddress("0x0000000000000000000000000000000000000000"),
		token1:   domain.MustParseAddress("0x1111111111111111111111111111111111111111"),
		feeBPS:   30,
		tier:     domain.TierA,
	}
}

func TestAdapter_Metadata(t *testing.T) {
	adapter := newTestAdapter()

	require.Equal(t, "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1", adapter.PoolID())
	require.Equal(t, domain.ChainBase, adapter.Chain())
	require.Equal(t, "aerodrome", adapter.Protocol())
	require.Equal(t, uint(30), adapter.FeeBPS())
	require.Equal(t, domain.TierA, adapter.Tier())

	// Verify Token0/Token1 return proper Address types
	token0 := adapter.Token0()
	token1 := adapter.Token1()
	require.NotEmpty(t, token0.String())
	require.NotEmpty(t, token1.String())
}

func TestAdapter_GetState(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	state, err := adapter.GetState(ctx)
	require.NoError(t, err)
	require.NotNil(t, state)
	require.NotNil(t, state.SqrtPriceX96)
	require.True(t, state.Tick != 0 || state.SqrtPriceX96.BitLen() > 0)
}

func TestAdapter_Quote(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	amount := decimal.NewFromInt(1000)
	zeroForOne := true

	result, err := adapter.Quote(ctx, amount, zeroForOne)
	require.NoError(t, err)
	require.NotNil(t, result)
	require.NotNil(t, result.Token.Address)
	require.True(t, result.Amount.GreaterThan(decimal.Zero))
}

func TestAdapter_Quote_DirectionSwap(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	amount := decimal.NewFromInt(1000)

	// Quote token0 -> token1
	result0to1, err := adapter.Quote(ctx, amount, true)
	require.NoError(t, err)

	// Quote token1 -> token0
	result1to0, err := adapter.Quote(ctx, amount, false)
	require.NoError(t, err)

	// Results should have different token addresses
	require.NotEqual(t, result0to1.Token.Address, result1to0.Token.Address)
}

func TestAdapter_BuildAddLiquidity(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	params := ports.AddLiquidityParams{
		Amount0:    decimal.NewFromInt(1000),
		Amount1:    decimal.NewFromInt(1000),
		MinAmount0: decimal.NewFromInt(900),
		MinAmount1: decimal.NewFromInt(900),
		Deadline:   1700000000,
		TickLower:  -100,
		TickUpper:  100,
		Recipient:  domain.MustParseAddress("0x2222222222222222222222222222222222222222"),
	}

	tx, err := adapter.BuildAddLiquidity(ctx, params)
	require.NoError(t, err)
	require.NotNil(t, tx)
	require.Equal(t, domain.ChainBase, tx.Chain)
	// Now sending to router instead of pool
	require.Equal(t, adapter.router, tx.To)
	// Verify calldata is not empty (proper ABI encoding)
	require.NotEmpty(t, tx.Data)
	require.Len(t, tx.Data, 4+32*8, "addLiquidity calldata should be 4 + 8*32 bytes")
}

func TestAdapter_BuildAddLiquidity_SingleSided(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	// Test adding only token0
	params := ports.AddLiquidityParams{
		Amount0:    decimal.NewFromInt(1000),
		Amount1:    decimal.Zero,
		MinAmount0: decimal.NewFromInt(900),
		Deadline:   1700000000,
		TickLower:  -100,
		TickUpper:  100,
		Recipient:  domain.MustParseAddress("0x2222222222222222222222222222222222222222"),
	}

	tx, err := adapter.BuildAddLiquidity(ctx, params)
	require.NoError(t, err)
	require.NotNil(t, tx)
}

func TestAdapter_BuildRemoveLiquidity(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	positionID := "test-position"
	liquidity := decimal.NewFromInt(1000000)

	tx, err := adapter.BuildRemoveLiquidity(ctx, positionID, liquidity)
	require.NoError(t, err)
	require.NotNil(t, tx)
	require.Equal(t, domain.ChainBase, tx.Chain)
	require.Equal(t, adapter.router, tx.To)
	// Verify calldata is not empty
	require.NotEmpty(t, tx.Data)
	require.Len(t, tx.Data, 4+32*5, "removeLiquidity calldata should be 4 + 5*32 bytes")
}

func TestAdapter_BuildCollectFees(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	// Use a valid address format for the gauge
	gaugeAddress := "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1"

	tx, err := adapter.BuildCollectFees(ctx, gaugeAddress)
	require.NoError(t, err)
	require.NotNil(t, tx)
	require.Equal(t, domain.ChainBase, tx.Chain)
	// Verify calldata is not empty
	require.NotEmpty(t, tx.Data)
	require.Len(t, tx.Data, 4+32, "claimFees calldata should be 4 + 32 bytes")
}

func TestAdapter_BuildSwap(t *testing.T) {
	adapter := newTestAdapter()
	ctx := context.Background()

	params := ports.SwapParams{
		Amount:     decimal.NewFromInt(1000),
		MinOut:     decimal.NewFromInt(900),
		Deadline:   1700000000,
		ZeroForOne: true,
		Recipient:  domain.MustParseAddress("0x2222222222222222222222222222222222222222"),
	}

	tx, err := adapter.BuildSwap(ctx, params)
	require.NoError(t, err)
	require.NotNil(t, tx)
	require.Equal(t, domain.ChainBase, tx.Chain)
	// Now sending to router instead of pool
	require.Equal(t, adapter.router, tx.To)
	// Verify calldata is not empty
	require.NotEmpty(t, tx.Data)
}

func TestAdapter_CompileTimeInterfaceAssertion(t *testing.T) {
	// This test ensures Adapter implements ports.V3Pool at compile time
	var _ ports.V3Pool = (*Adapter)(nil)
}