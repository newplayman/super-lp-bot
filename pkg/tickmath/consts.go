package tickmath

import "math/big"

const (
	MIN_TICK int64 = -887272
	MAX_TICK int64 = 887272
	Q96      = 0x1000000000000000000000000 // 2^96 as int64 (use big.Int for actual use)
)

// Q96Big is 2^96 as a big.Int
var Q96Big = new(big.Int).Lsh(big.NewInt(1), 96)

// Q192Big is 2^192 as a big.Int (Q96^2)
var Q192Big = new(big.Int).Lsh(big.NewInt(1), 192)

// MinTick / MaxTick constants
var MinTick = MIN_TICK
var MaxTick = MAX_TICK

// IsValidTick returns true if tick is within V3 valid range.
func IsValidTick(tick int64) bool {
	return tick >= MIN_TICK && tick <= MAX_TICK
}
