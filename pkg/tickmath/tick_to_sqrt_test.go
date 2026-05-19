package tickmath_test

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/lpbot/lpbot/pkg/tickmath"
)

func TestTickToSqrtPriceX96_Tick0(t *testing.T) {
	// sqrt(1) * 2^96 = 2^96
	result, err := tickmath.TickToSqrtPriceX96(0)
	require.NoError(t, err)
	require.Equal(t, tickmath.Q96Big.String(), result.String())
}

func TestTickToSqrtPriceX96_Tick1(t *testing.T) {
	result, err := tickmath.TickToSqrtPriceX96(1)
	require.NoError(t, err)
	// sqrt(1.0001) * 2^96 ≈ 79228162514264337593543950345
	require.True(t, result.BitLen() > 0)
}

func TestTickToSqrtPriceX96_Invalid(t *testing.T) {
	_, err := tickmath.TickToSqrtPriceX96(-887273)
	require.Error(t, err)
	_, err = tickmath.TickToSqrtPriceX96(887273)
	require.Error(t, err)
}