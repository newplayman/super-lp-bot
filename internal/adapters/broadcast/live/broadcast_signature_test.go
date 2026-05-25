//go:build live

package live

import (
	"testing"

	"github.com/gagliardetto/solana-go"
	"github.com/stretchr/testify/require"
)

func TestFirstSolanaSignature(t *testing.T) {
	sig, err := solana.SignatureFromBase58("5YBLhMBLjhAHnEPnHKLLnVwHSfXGPJMCvKAfNsiaEw2T63edrYxVFHKUxRXfP6KA1HVo7c9JZ3LAJQR72giX7Cb")
	require.NoError(t, err)

	got, err := firstSolanaSignature(&solana.Transaction{
		Signatures: []solana.Signature{sig},
	})
	require.NoError(t, err)
	require.Equal(t, sig, got)
}

func TestFirstSolanaSignature_RequiresPrimarySignature(t *testing.T) {
	_, err := firstSolanaSignature(&solana.Transaction{})
	require.Error(t, err)
}
