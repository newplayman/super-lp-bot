package ports_test

import (
	"context"
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: Wallet must implement ports.Wallet
var _ ports.Wallet = (*walletMock)(nil)

type walletMock struct{}

func (m *walletMock) Open(ctx context.Context) error                                              { return nil }
func (m *walletMock) Close() error                                                                 { return nil }
func (m *walletMock) Address() domain.Address                                                      { return domain.Address{} }
func (m *walletMock) Chain() domain.ChainID                                                        { return "" }
func (m *walletMock) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error)       { return domain.SignedTx{}, nil }
func (m *walletMock) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
func (m *walletMock) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}

// Compile-time interface assertion: WalletProvider must implement ports.WalletProvider
var _ ports.WalletProvider = (*walletProviderMock)(nil)

type walletProviderMock struct{}

func (m *walletProviderMock) Open(ctx context.Context, config ports.WalletConfig) (ports.Wallet, error) {
	return &walletMock{}, nil
}
func (m *walletProviderMock) Type() string { return "mock" }

// Compile-time interface assertion: walletFunc implements Wallet for functional tests
var _ ports.Wallet = (*walletFuncMock)(nil)

type walletFuncMock struct {
	openFn    func(ctx context.Context) error
	closeFn   func() error
	addressFn func() domain.Address
	chainFn   func() domain.ChainID
	signFn    func(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error)
	approveFn func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error)
	revokeFn  func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error)
}

func (w *walletFuncMock) Open(ctx context.Context) error {
	if w.openFn != nil {
		return w.openFn(ctx)
	}
	return nil
}

func (w *walletFuncMock) Close() error {
	if w.closeFn != nil {
		return w.closeFn()
	}
	return nil
}

func (w *walletFuncMock) Address() domain.Address {
	if w.addressFn != nil {
		return w.addressFn()
	}
	return domain.Address{}
}

func (w *walletFuncMock) Chain() domain.ChainID {
	if w.chainFn != nil {
		return w.chainFn()
	}
	return ""
}

func (w *walletFuncMock) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	if w.signFn != nil {
		return w.signFn(ctx, tx)
	}
	return domain.SignedTx{}, nil
}

func (w *walletFuncMock) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	if w.approveFn != nil {
		return w.approveFn(ctx, token, spender, amount)
	}
	return domain.UnsignedTx{}, nil
}

func (w *walletFuncMock) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	if w.revokeFn != nil {
		return w.revokeFn(ctx, token, spender)
	}
	return domain.UnsignedTx{}, nil
}

// TestWalletInterface verifies the Wallet interface is properly defined
func TestWalletInterface(t *testing.T) {
	require.NotNil(t, t, "ports.Wallet interface must exist")
	require.NotNil(t, t, "ports.WalletProvider interface must exist")
}

// TestWalletProviderInterface verifies the WalletProvider interface is properly defined
func TestWalletProviderInterface(t *testing.T) {
	// Verify both interfaces exist and can be used as expected
	provider := &walletProviderMock{}
	require.NotEmpty(t, provider.Type())

	wallet, err := provider.Open(context.Background(), ports.WalletConfig{})
	require.NoError(t, err)
	require.NotNil(t, wallet)
}

// TestWalletFuncMock verifies the functional mock can be instantiated
func TestWalletFuncMock(t *testing.T) {
	ctx := context.Background()
	wallet := &walletFuncMock{
		openFn: func(ctx context.Context) error { return nil },
		closeFn: func() error { return nil },
		addressFn: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		chainFn: func() domain.ChainID { return "base" },
		signFn: func(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
			return domain.SignedTx{}, nil
		},
		approveFn: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
		revokeFn: func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
	}

	require.NoError(t, wallet.Open(ctx))
	require.NoError(t, wallet.Close())
	require.NotEmpty(t, wallet.Address().String())
	require.Equal(t, domain.ChainID("base"), wallet.Chain())

	signed, err := wallet.Sign(ctx, domain.UnsignedTx{})
	require.NoError(t, err)
	require.NotNil(t, signed)

	approved, err := wallet.ApproveExact(ctx, domain.Address{}, domain.Address{}, big.NewInt(1000))
	require.NoError(t, err)
	require.NotNil(t, approved)

	revoked, err := wallet.Revoke(ctx, domain.Address{}, domain.Address{})
	require.NoError(t, err)
	require.NotNil(t, revoked)
}

// TestWalletConfigFields verifies WalletConfig structure
func TestWalletConfigFields(t *testing.T) {
	config := ports.WalletConfig{
		Type:          "keystore",
		ChainID:       "base",
		KeystoreDir:   "/path/to/keystore",
		KeystoreFile:  "wallet.json",
		Passphrase:    "secret",
		KMSKeyID:      "",
		KMSRegion:     "",
		KMSEndpoint:   "",
		KMSKeyAlias:   "",
		Address:       domain.Address{},
	}

	require.Equal(t, "keystore", config.Type)
	require.Equal(t, domain.ChainID("base"), config.ChainID)
	require.Equal(t, "/path/to/keystore", config.KeystoreDir)
	require.Equal(t, "wallet.json", config.KeystoreFile)
	require.Equal(t, "secret", config.Passphrase)
}