// Package aerodrome provides the Aerodrome pool adapter implementation.
package aerodrome

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// Protocol name for Aerodrome
const ProtocolName = "aerodrome"

// Adapter implements ports.V3Pool for Aerodrome V2 on Base chain.
// Aerodrome is a stable swap AMM with CLMM-like mechanics.
type Adapter struct {
	poolID   string
	chain    domain.ChainID
	protocol string
	token0   domain.Address
	token1   domain.Address
	feeBPS   uint
	tier     domain.Tier
}

// NewAdapter creates a new Aerodrome pool adapter.
func NewAdapter(poolID, token0, token1 string, feeBPS uint, tier domain.Tier) *Adapter {
	return &Adapter{
		poolID:   poolID,
		chain:    domain.ChainBase,
		protocol: ProtocolName,
		token0:   domain.MustParseAddress(token0),
		token1:   domain.MustParseAddress(token1),
		feeBPS:   feeBPS,
		tier:     tier,
	}
}

// PoolID returns the pool identifier.
func (a *Adapter) PoolID() string { return a.poolID }

// Chain returns the chain identifier.
func (a *Adapter) Chain() domain.ChainID { return a.chain }

// Protocol returns the protocol name.
func (a *Adapter) Protocol() string { return a.protocol }

// Token0 returns the first token address.
func (a *Adapter) Token0() domain.Address { return a.token0 }

// Token1 returns the second token address.
func (a *Adapter) Token1() domain.Address { return a.token1 }

// FeeBPS returns the pool fee in basis points.
func (a *Adapter) FeeBPS() uint { return a.feeBPS }

// Tier returns the risk tier.
func (a *Adapter) Tier() domain.Tier { return a.tier }

// GetState returns the current state of the Aerodrome pool.
func (a *Adapter) GetState(ctx interface{}) (domain.PoolState, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}

	// Aerodrome V2 has a simplified state compared to CLMM.
	// Return pool state with available data.
	state := domain.PoolState{
		BlockRef: domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   0,
			Hash:     "",
			TimeUnix: 0,
		},
		// Aerodrome uses virtual reserves; we'll compute sqrtPrice from observation.
		SqrtPriceX96: big.NewInt(1),
		Tick:         0,
		Liquidity:    big.NewInt(0),
	}

	_ = c
	return state, nil
}

// Quote returns the expected output amount for a swap.
func (a *Adapter) Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}

	// Aerodrome fee is 0.02% (2 bps) for stable pairs, varies for volatile.
	// Use the pool's configured feeBPS instead.
	feeMultiplier := decimal.NewFromFloat(1.0).Sub(
		decimal.NewFromInt(int64(a.feeBPS)).Div(decimal.NewFromInt(10000)),
	)

	// Simple constant product / stable swap quote.
	outputAmount := amount.Mul(feeMultiplier)

	// Determine output token based on direction.
	var outputToken domain.Token
	if zeroForOne {
		outputToken = domain.Token{
			Address:  a.token1,
			Symbol:   "",
			Decimals: 18,
			Chain:    domain.ChainBase,
		}
	} else {
		outputToken = domain.Token{
			Address:  a.token0,
			Symbol:   "",
			Decimals: 18,
			Chain:    domain.ChainBase,
		}
	}

	_ = c
	return domain.TokenAmount{
		Token:  outputToken,
		Amount: outputAmount,
	}, nil
}

// BuildAddLiquidity constructs an unsigned transaction to add liquidity.
func (a *Adapter) BuildAddLiquidity(ctx interface{}, params ports.AddLiquidityParams) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}

	// Validate deadline (invariant #4)
	if params.Deadline == 0 {
		panic("deadline is required (invariant #4)")
	}

	// Build the add liquidity calldata.
	// For Aerodrome V2, we use addLiquidity on the gauge contract.
	data := buildAddLiquidityData(params)

	tx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		From:     params.Recipient, // Will be filled by signer
		To:       domain.MustParseAddress(a.poolID),
		Data:     data,
		Value:    domain.Decimal{},
		Deadline: params.Deadline,
		MinOut:   params.MinAmount1, // For single-sided, this is the expected amount
	}

	_ = c
	return tx, nil
}

// BuildRemoveLiquidity constructs an unsigned transaction to remove liquidity.
func (a *Adapter) BuildRemoveLiquidity(ctx interface{}, positionID string, liquidity domain.Decimal) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}

	// Build the remove liquidity calldata.
	data := buildRemoveLiquidityData(positionID, liquidity)

	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		To:    domain.MustParseAddress(a.poolID),
		Data:  data,
	}

	_ = c
	return tx, nil
}

// BuildCollectFees constructs an unsigned transaction to collect accumulated fees.
func (a *Adapter) BuildCollectFees(ctx interface{}, positionID string) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}

	// Aerodrome uses a claimable flow for fees.
	data := buildCollectFeesData(positionID)

	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		To:    domain.MustParseAddress(a.poolID),
		Data:  data,
	}

	_ = c
	return tx, nil
}

// BuildSwap constructs an unsigned transaction to execute a swap.
func (a *Adapter) BuildSwap(ctx interface{}, params ports.SwapParams) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}

	// Validate deadline (invariant #4)
	if params.Deadline == 0 {
		panic("deadline is required (invariant #4)")
	}

	// Build the swap calldata.
	data := buildSwapData(params)

	tx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		From:     params.Recipient, // Will be filled by signer
		To:       domain.MustParseAddress(a.poolID),
		Data:     data,
		Value:    domain.Decimal{},
		Deadline: params.Deadline,
		MinOut:   params.MinOut,
	}

	_ = c
	return tx, nil
}

// buildAddLiquidityData constructs calldata for adding liquidity.
// TODO: Implement actual ABI encoding for Aerodrome's addLiquidity.
func buildAddLiquidityData(params ports.AddLiquidityParams) []byte {
	// Placeholder calldata - actual implementation would encode:
	// function addLiquidity(address pool, uint256 amount0, uint256 amount1, address to)
	_ = params
	return []byte{}
}

// buildRemoveLiquidityData constructs calldata for removing liquidity.
func buildRemoveLiquidityData(positionID string, liquidity domain.Decimal) []byte {
	// Placeholder calldata - actual implementation would encode:
	// function removeLiquidity(address pool, uint256 liquidity, address to)
	_ = positionID
	_ = liquidity
	return []byte{}
}

// buildCollectFeesData constructs calldata for collecting fees.
func buildCollectFeesData(positionID string) []byte {
	// Aerodrome uses claimFees() function
	// function claimFees(address pool) returns (uint256, uint256)
	_ = positionID
	return []byte{}
}

// buildSwapData constructs calldata for executing a swap.
func buildSwapData(params ports.SwapParams) []byte {
	// Placeholder calldata - actual implementation would encode:
	// function swap(address tokenIn, uint256 amountIn, uint256 minOut, address to)
	_ = params
	return []byte{}
}

// Compile-time interface assertion
var _ ports.V3Pool = (*Adapter)(nil)