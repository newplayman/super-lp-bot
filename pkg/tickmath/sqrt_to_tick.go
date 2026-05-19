package tickmath

import (
	"errors"
	"math/big"
)

var ErrInvalidSqrtPrice = errors.New("invalid sqrt price")

// SqrtPriceX96ToTick converts sqrtPriceX96 to tick.
// Returns floor of log_{sqrt(1.0001)}(sqrtPriceX96/2^96).
func SqrtPriceX96ToTick(sqrtPriceX96 *big.Int) (int, error) {
	if sqrtPriceX96 == nil || sqrtPriceX96.Sign() <= 0 {
		return 0, ErrInvalidSqrtPrice
	}

	// Reference: Uniswap V3 TickMath.getTickAtSqrtRatio
	// tick = floor(log_{1.0001}((sqrtPriceX96 / 2^96)^2))
	// = floor(2 * log_{1.0001}(sqrtPriceX96 / 2^96))

	// Simplified: binary search from MIN_TICK to MAX_TICK
	lo := MIN_TICK
	hi := MAX_TICK
	for lo <= hi {
		mid := (lo + hi) / 2
		sqrtAtMid, _ := TickToSqrtPriceX96(mid)

		cmp := sqrtPriceX96.Cmp(sqrtAtMid)
		if cmp == 0 {
			return int(mid), nil
		} else if cmp > 0 {
			lo = mid + 1
		} else {
			hi = mid - 1
		}
	}
	// Return floor: hi is always < target, lo is always > target
	return int(hi), nil
}
