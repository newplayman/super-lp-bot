// Package ports defines the interface abstractions (hexagonal architecture ports).
//
// The ports layer provides contracts that adapters must satisfy. Core packages
// depend only on these interfaces, never on concrete adapter implementations.
//
// Pool interfaces (V2Pool, V3Pool) define the contract for interacting with
// AMM liquidity pools across different protocol versions.
package ports

import (
	"github.com/lpbot/lpbot/internal/domain"
)

// V3Pool defines the interface for V3-style CLMM (Concentrated Liquidity Market Maker) pools
// such as Uniswap V3, Orca Whirlpool, and Aerodrome. These pools operate with
// discrete tick ranges and fee tiers.
//
// V3 pools support:
//   - Concentrated liquidity (position-based liquidity)
//   - Multiple fee tiers (0.05%, 0.3%, 1%, etc.)
//   - Tick-based price representation
//   - Fee accumulation per position
type V3Pool interface {
	PoolMetadata

	// GetState returns the current state of the pool at the given block reference.
	// Returns PoolState with SqrtPriceX96, Tick, and Liquidity populated.
	// ctx is the execution context (e.g., context.Context).
	GetState(ctx interface{}) (domain.PoolState, error)

	// Quote returns the expected output amount for a given input amount.
	// zeroForOne indicates direction: true = token0 → token1, false = token1 → token0.
	// Returns the output TokenAmount and any error encountered.
	Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error)

	// BuildAddLiquidity constructs an unsigned transaction to add liquidity to the pool.
	// The params specify tick range, amount, and slippage tolerance.
	BuildAddLiquidity(ctx interface{}, params AddLiquidityParams) (domain.UnsignedTx, error)

	// BuildRemoveLiquidity constructs an unsigned transaction to remove liquidity from a position.
	// positionID identifies the position to remove from.
	// liquidity specifies the amount of liquidity to remove (use full position liquidity for full removal).
	BuildRemoveLiquidity(ctx interface{}, positionID string, liquidity domain.Decimal) (domain.UnsignedTx, error)

	// BuildCollectFees constructs an unsigned transaction to collect accumulated fees
	// from a position. Only fees are collected, not the principal liquidity.
	BuildCollectFees(ctx interface{}, positionID string) (domain.UnsignedTx, error)

	// BuildSwap constructs an unsigned transaction to execute a swap.
	// zeroForOne indicates swap direction (see Quote).
	BuildSwap(ctx interface{}, params SwapParams) (domain.UnsignedTx, error)
}

// V2Pool defines the interface for V2-style constant-product AMM pools
// such as Uniswap V2 and SushiSwap. These pools operate with
// a simple x*y=k formula and do not support concentrated liquidity.
//
// V2 pools support:
//   - Simple constant-product pricing
//   - Single fee tier per pool
//   - Reserve-based liquidity (no positions)
type V2Pool interface {
	PoolMetadata

	// GetState returns the current state of the pool.
	// Returns PoolState with Reserve0 and Reserve1 populated.
	// SqrtPriceX96 will be nil (V2 pools use reserves, not sqrtPriceX96).
	GetState(ctx interface{}) (domain.PoolState, error)

	// Quote returns the expected output amount for a given input amount.
	// zeroForOne indicates direction: true = token0 → token1, false = token1 → token0.
	Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error)

	// BuildAddLiquidity constructs an unsigned transaction to add liquidity to the pool.
	// For V2, this is a simple mint operation with symmetric token amounts.
	BuildAddLiquidity(ctx interface{}, params AddLiquidityParams) (domain.UnsignedTx, error)

	// BuildRemoveLiquidity constructs an unsigned transaction to remove liquidity.
	// For V2, params specify the liquidity token burn amount.
	BuildRemoveLiquidity(ctx interface{}, params RemoveLiquidityParams) (domain.UnsignedTx, error)

	// BuildSwap constructs an unsigned transaction to execute a swap.
	BuildSwap(ctx interface{}, params SwapParams) (domain.UnsignedTx, error)
}

// PoolMetadata contains the immutable metadata for a pool.
// Both V2Pool and V3Pool embed this interface.
type PoolMetadata interface {
	// PoolID returns the on-chain pool address.
	PoolID() string

	// Chain returns the chain identifier.
	Chain() domain.ChainID

	// Protocol returns the protocol name (e.g., "uniswap_v3", "uniswap_v2", "whirlpool").
	Protocol() string

	// Token0 returns the first token address in the pair.
	Token0() domain.Address

	// Token1 returns the second token address in the pair.
	Token1() domain.Address

	// FeeBPS returns the pool fee in basis points (e.g., 30 = 0.3%).
	FeeBPS() uint

	// Tier returns the assigned risk tier for this pool.
	Tier() domain.Tier
}

// AddLiquidityParams contains parameters for adding liquidity to a pool.
type AddLiquidityParams struct {
	// Amount0 is the amount of token0 to add (may be zero if only adding token1).
	Amount0 domain.Decimal

	// Amount1 is the amount of token1 to add (may be zero if only adding token0).
	Amount1 domain.Decimal

	// MinAmount0 is the minimum amount of token0 to receive (slippage protection).
	// If the actual amount is less, the transaction will revert.
	MinAmount0 domain.Decimal

	// MinAmount1 is the minimum amount of token1 to receive (slippage protection).
	MinAmount1 domain.Decimal

	// Deadline is the unix timestamp after which the transaction expires.
	// Zero value will cause panic (invariant #4).
	Deadline int64

	// TickLower is the lower bound of the tick range (V3 only).
	// Ignored for V2 pools.
	TickLower int64

	// TickUpper is the upper bound of the tick range (V3 only).
	// Ignored for V2 pools.
	TickUpper int64

	// Recipient is the address that will receive the liquidity position.
	Recipient domain.Address
}

// RemoveLiquidityParams contains parameters for removing liquidity from a V2 pool.
type RemoveLiquidityParams struct {
	// Liquidity is the amount of liquidity tokens to burn.
	// Use the full position's liquidity for complete removal.
	Liquidity domain.Decimal

	// MinAmount0 is the minimum amount of token0 to receive.
	MinAmount0 domain.Decimal

	// MinAmount1 is the minimum amount of token1 to receive.
	MinAmount1 domain.Decimal

	// Deadline is the unix timestamp after which the transaction expires.
	// Zero value will cause panic (invariant #4).
	Deadline int64

	// Recipient is the address that will receive the reclaimed tokens.
	Recipient domain.Address
}

// SwapParams contains parameters for executing a swap.
type SwapParams struct {
	// Amount is the input amount for the swap.
	// The token direction is determined by zeroForOne.
	Amount domain.Decimal

	// MinOut is the minimum output amount (slippage protection).
	// If the actual output is less, the transaction will revert.
	// Zero value will cause panic (invariant #4).
	MinOut domain.Decimal

	// Deadline is the unix timestamp after which the transaction expires.
	// Zero value will cause panic (invariant #4).
	Deadline int64

	// ZeroForOne indicates the swap direction.
	// true: input is token0, output is token1
	// false: input is token1, output is token0
	ZeroForOne bool

	// Recipient is the address that will receive the output tokens.
	Recipient domain.Address
}
