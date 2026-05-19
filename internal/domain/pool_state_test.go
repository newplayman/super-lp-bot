package domain_test

import (
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestPoolState_IsV3(t *testing.T) {
	one := big.NewInt(1)
	s := domain.PoolState{
		SqrtPriceX96: new(big.Int).Lsh(one, 96), // 2^96
		Tick:      100,
		Liquidity: one,
	}
	require.True(t, s.IsV3())
	require.False(t, s.IsV2())
}

func TestPoolState_IsV2(t *testing.T) {
	s := domain.PoolState{
		Reserve0: domain.MustDecimal("1000000"),
		Reserve1: domain.MustDecimal("1000000"),
	}
	require.True(t, s.IsV2())
	require.False(t, s.IsV3())
}
