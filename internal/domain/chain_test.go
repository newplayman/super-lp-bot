package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestChainID_Known(t *testing.T) {
	require.Equal(t, "base", domain.ChainBase.String())
	require.Equal(t, "solana", domain.ChainSolana.String())
}

func TestChainID_Parse(t *testing.T) {
	c, err := domain.ParseChainID("base")
	require.NoError(t, err)
	require.Equal(t, domain.ChainBase, c)

	_, err = domain.ParseChainID("ethereum")  // Phase 1–3 范围外
	require.Error(t, err)
}

func TestBlockRef_Equal(t *testing.T) {
	a := domain.BlockRef{Chain: domain.ChainBase, Number: 100, Hash: "0xabc"}
	b := domain.BlockRef{Chain: domain.ChainBase, Number: 100, Hash: "0xabc"}
	require.True(t, a.Equal(b))

	c := domain.BlockRef{Chain: domain.ChainBase, Number: 100, Hash: "0xdef"}
	require.False(t, a.Equal(c))  // hash 变化即不等（reorg 检测）
}