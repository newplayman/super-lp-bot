package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestAddress_EVM(t *testing.T) {
	a := domain.MustParseAddress("0x0000000000000000000000000000000000000000")
	require.Equal(t, domain.ChainBase, a.Chain())
	require.True(t, a.IsZero())
	require.Equal(t, "0x0000000000000000000000000000000000000000", a.String())
}

func TestAddress_EVM_Valid(t *testing.T) {
	a, err := domain.ParseAddress("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")
	require.NoError(t, err)
	require.Equal(t, domain.ChainBase, a.Chain())
	require.Len(t, a.Bytes(), 20)
}

func TestAddress_EVM_Invalid(t *testing.T) {
	_, err := domain.ParseAddress("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2_extra")
	require.Error(t, err)
	_, err = domain.ParseAddress("not-an-address")
	require.Error(t, err)
}

func TestAddress_Solana(t *testing.T) {
	// Example Solana address (Raydium LP token)
	a := domain.MustParseAddress("AfuCtBJFEcFjXTBt4eGDREQKKuNdJ6iUd6EBJnL3cr7")
	require.Equal(t, domain.ChainSolana, a.Chain())
	require.Len(t, a.Bytes(), 32)
}

func TestAddress_Solana_Invalid(t *testing.T) {
	_, err := domain.ParseAddress("invalid")
	require.Error(t, err)
}