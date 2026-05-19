package kms_test

import (
	"context"
	"errors"
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/internal/adapters/wallet/kms"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestKMSWalletProviderType verifies the provider returns correct type.
func TestKMSWalletProviderType(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	require.Equal(t, "kms", provider.Type())
}

// TestKMSWalletProviderOpenWithoutConfig verifies error on missing config.
func TestKMSWalletProviderOpenWithoutConfig(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	_, err := provider.Open(context.Background(), ports.WalletConfig{})
	require.Error(t, err)
	require.Contains(t, err.Error(), "KMSKeyID")
	require.Contains(t, err.Error(), "KMSKeyAlias")
}

// TestKMSWalletProviderOpenWithKeyID verifies provider opens with key ID.
func TestKMSWalletProviderOpenWithKeyID(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)
	require.NotNil(t, wallet)
}

// TestKMSWalletProviderOpenWithKeyAlias verifies provider opens with key alias.
func TestKMSWalletProviderOpenWithKeyAlias(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyAlias: "alias/my-key",
		ChainID:     domain.ChainSolana,
	})
	require.NoError(t, err)
	require.NotNil(t, wallet)
}

// TestKMSWalletOpenClose verifies Open/Close lifecycle.
func TestKMSWalletOpenClose(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	require.NoError(t, wallet.Open(context.Background()))
	require.NoError(t, wallet.Close())
}

// TestKMSWalletSignNotOpen verifies Sign fails when not open.
func TestKMSWalletSignNotOpen(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	_, err = wallet.Sign(context.Background(), domain.UnsignedTx{})
	require.Error(t, err)
	require.True(t, errors.Is(err, kms.ErrNotOpen))
}

// TestKMSWalletApproveNotOpen verifies ApproveExact fails when not open.
func TestKMSWalletApproveNotOpen(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	_, err = wallet.ApproveExact(context.Background(), domain.Address{}, domain.Address{}, big.NewInt(1000))
	require.Error(t, err)
	require.True(t, errors.Is(err, kms.ErrNotOpen))
}

// TestKMSWalletRevokeNotOpen verifies Revoke fails when not open.
func TestKMSWalletRevokeNotOpen(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	_, err = wallet.Revoke(context.Background(), domain.Address{}, domain.Address{})
	require.Error(t, err)
	require.True(t, errors.Is(err, kms.ErrNotOpen))
}

// TestKMSWalletApproveStub verifies ApproveExact returns not implemented error.
func TestKMSWalletApproveStub(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	require.NoError(t, wallet.Open(context.Background()))
	_, err = wallet.ApproveExact(context.Background(), domain.Address{}, domain.Address{}, big.NewInt(1000))
	require.Error(t, err)
	require.True(t, errors.Is(err, kms.ErrNotImplemented))
}

// TestKMSWalletRevokeStub verifies Revoke returns not implemented error.
func TestKMSWalletRevokeStub(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	require.NoError(t, wallet.Open(context.Background()))
	_, err = wallet.Revoke(context.Background(), domain.Address{}, domain.Address{})
	require.Error(t, err)
	require.True(t, errors.Is(err, kms.ErrNotImplemented))
}

// TestKMSWalletSignStub verifies Sign returns stub signature when open.
func TestKMSWalletSignStub(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainBase,
	})
	require.NoError(t, err)

	require.NoError(t, wallet.Open(context.Background()))
	signed, err := wallet.Sign(context.Background(), domain.UnsignedTx{
		Chain:  domain.ChainBase,
		Nonce:  42,
		MinOut: domain.MustDecimal("100"),
	})
	require.NoError(t, err)
	require.NotEmpty(t, signed.Signature)
	require.NotEmpty(t, signed.Hash)
}

// TestKMSWalletChain verifies Chain returns correct chain ID.
func TestKMSWalletChain(t *testing.T) {
	provider := kms.NewKMSWalletProvider()
	wallet, err := provider.Open(context.Background(), ports.WalletConfig{
		KMSKeyID: "key-12345",
		ChainID:  domain.ChainSolana,
	})
	require.NoError(t, err)

	require.Equal(t, domain.ChainSolana, wallet.Chain())
}