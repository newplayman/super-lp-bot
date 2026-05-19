package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestPool_Key(t *testing.T) {
	p := domain.Pool{
		ID:       "0x1234",
		Chain:    domain.ChainBase,
		Protocol: "uniswap_v3",
	}
	require.Equal(t, "base:uniswap_v3:0x1234", p.Key())
}

func TestPool_IsActive(t *testing.T) {
	active := domain.Pool{TVLUSD: domain.MustDecimal("1000000")}
	inactive := domain.Pool{TVLUSD: domain.MustDecimal("0")}
	require.True(t, active.IsActive())
	require.False(t, inactive.IsActive())
}

func TestPool_String(t *testing.T) {
	p := domain.Pool{ID: "0x123", Chain: domain.ChainBase, Protocol: "uniswap_v3"}
	s := p.String()
	require.Contains(t, s, "0x123")
	require.Contains(t, s, "uniswap_v3")
}