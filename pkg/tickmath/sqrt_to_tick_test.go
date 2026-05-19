package tickmath_test

import (
	"math/big"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"pgregory.net/rapid"
)

func TestSqrtPriceX96ToTick_Tick0(t *testing.T) {
	// sqrtPriceX96 = 2^96 should give tick 0
	result, err := tickmath.SqrtPriceX96ToTick(tickmath.Q96Big)
	require.NoError(t, err)
	require.Equal(t, 0, result)
}

func TestSqrtPriceX96ToTick_Invalid(t *testing.T) {
	_, err := tickmath.SqrtPriceX96ToTick(big.NewInt(0))
	require.Error(t, err)
	_, err = tickmath.SqrtPriceX96ToTick(big.NewInt(-1))
	require.Error(t, err)
}

// Property test: SqrtPriceX96ToTick(TickToSqrtPriceX96(t)) ≈ t
func TestTick_SqrtRoundtrip(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		tick := rapid.Int64Range(tickmath.MIN_TICK, tickmath.MAX_TICK).Draw(t, "tick")
		sqrt, err := tickmath.TickToSqrtPriceX96(tick)
		if err != nil {
			t.Fatalf("TickToSqrtPriceX96(%d) error: %v", tick, err)
		}
		result, err := tickmath.SqrtPriceX96ToTick(sqrt)
		if err != nil {
			t.Fatalf("SqrtPriceX96ToTick error: %v", err)
		}
		// roundtrip may differ by 1 due to floor
		diff := result - int(tick)
		if diff < 0 {
			diff = -diff
		}
		require.True(t, diff <= 1, "roundtrip tick=%d got=%d diff=%d", tick, result, diff)
	})
}
