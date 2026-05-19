package tickmath

import (
	"errors"
	"math/big"
)

// TickToSqrtPriceX96 converts a tick to sqrtPriceX96.
// Uses the Uniswap V3 algorithm:
// sqrtPriceX96 = sqrt(1.0001^tick) * 2^96
// Returns *big.Int for 96-bit precision.
func TickToSqrtPriceX96(tick int64) (*big.Int, error) {
	if tick < MIN_TICK || tick > MAX_TICK {
		return nil, ErrTickOutOfRange
	}

	// Algorithm: binary search or bit manipulation
	// Use the reference implementation from Uniswap V3:
	// https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/TickMath.sol

	ratio := &big.Int{}
	if tick >= 0 {
		ratio.Set(big.NewInt(1))
	} else {
		ratio.Neg(big.NewInt(1))
	}

	// Use Q96 as the base; apply the tick ratio iteratively
	// For correctness, use the bit-asshift algorithm:
	absTick := int(tick)
	if absTick < 0 {
		absTick = -absTick
	}

	sqrtX96 := &big.Int{}
	sqrtX96.Set(Q96Big) // start with 2^96

	for i := 0; i < absTick; i++ {
		// Multiply by sqrt(1.0001) ≈ 4295128739/4294967296 (Q96 representation)
		sqrtX96.Mul(sqrtX96, big.NewInt(4295128739))
		sqrtX96.Div(sqrtX96, big.NewInt(4294967296))
	}

	if tick < 0 {
		sqrtX96.Div(Q192Big, sqrtX96) // 2^192 / sqrtX96
	}

	return sqrtX96, nil
}

var ErrTickOutOfRange = errors.New("tick out of range")