package tickmath_test

import (
	"math/big"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/lpbot/lpbot/pkg/tickmath"
)

func TestConstants(t *testing.T) {
	require.Equal(t, int64(-887272), tickmath.MIN_TICK)
	require.Equal(t, int64(887272), tickmath.MAX_TICK)
}

func TestQ96(t *testing.T) {
	expected, _ := new(big.Int).SetString("79228162514264337593543950336", 10) // 2^96
	require.Equal(t, expected.String(), tickmath.Q96Big.String())
}

func TestIsValidTick(t *testing.T) {
	require.True(t, tickmath.IsValidTick(0))
	require.True(t, tickmath.IsValidTick(-887272))
	require.True(t, tickmath.IsValidTick(887272))
	require.False(t, tickmath.IsValidTick(-887273))
	require.False(t, tickmath.IsValidTick(887273))
}
