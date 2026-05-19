package domain

import "math/big"

// PoolState represents the state of a pool at a given block.
// V2 pools: Reserve0/1 set, SqrtPriceX96 = 0
// V3/CLMM pools: SqrtPriceX96/Tick/Liquidity set, Reserves may be 0
type PoolState struct {
	BlockRef BlockRef

	// V2 fields
	Reserve0 Decimal
	Reserve1 Decimal

	// V3 / CLMM fields
	SqrtPriceX96 *big.Int // 96-bit fixed point
	Tick         int64
	Liquidity    *big.Int // stored as big.Int for precision

	// V3 fee growth
	FeeGrowthGlobal0X128 *big.Int
	FeeGrowthGlobal1X128 *big.Int
}

// IsV3 returns true if this is a V3/CLMM pool state.
func (s PoolState) IsV3() bool {
	return s.SqrtPriceX96 != nil && s.SqrtPriceX96.BitLen() > 0
}

// IsV2 returns true if this is a V2 constant-product pool.
func (s PoolState) IsV2() bool {
	return s.SqrtPriceX96 == nil || s.SqrtPriceX96.BitLen() == 0
}
