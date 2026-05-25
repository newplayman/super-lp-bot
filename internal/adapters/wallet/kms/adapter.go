// Package kms provides a wallet adapter backed by AWS KMS (Key Management Service).
//
// This adapter uses AWS KMS for secure transaction signing, keeping private key
// material within the AWS security boundary. Phase 4 feature.
package kms

import (
	"context"
	"errors"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Compile-time interface assertion: KMSWallet implements ports.Wallet
var _ ports.Wallet = (*KMSWallet)(nil)

// Compile-time interface assertion: KMSWalletProvider implements ports.WalletProvider
var _ ports.WalletProvider = (*KMSWalletProvider)(nil)

// ErrNotOpen is returned when operations are attempted before Open is called.
var ErrNotOpen = errors.New("wallet not open: call Open first")

// ErrNotImplemented is returned for operations not yet implemented in Phase 4.
var ErrNotImplemented = errors.New("not implemented: Phase 4 stub")

// KMSWallet implements ports.Wallet using AWS KMS for signing.
type KMSWallet struct {
	keyID     string
	region    string
	endpoint  string
	keyAlias  string
	address   domain.Address
	chainID   domain.ChainID
	isOpen    bool
}

// KMSWalletProvider implements ports.WalletProvider for KMS-backed wallets.
type KMSWalletProvider struct{}

// NewKMSWalletProvider creates a new KMS wallet provider.
func NewKMSWalletProvider() *KMSWalletProvider {
	return &KMSWalletProvider{}
}

// Open creates a new KMSWallet instance using the provided configuration.
// The config must have KMSKeyID or KMSKeyAlias set.
func (p *KMSWalletProvider) Open(ctx context.Context, config ports.WalletConfig) (ports.Wallet, error) {
	if config.KMSKeyID == "" && config.KMSKeyAlias == "" {
		return nil, errors.New("KmsWallet: either KMSKeyID or KMSKeyAlias must be set")
	}

	wallet := &KMSWallet{
		keyID:    config.KMSKeyID,
		region:   config.KMSRegion,
		endpoint: config.KMSEndpoint,
		keyAlias: config.KMSKeyAlias,
		chainID:  config.ChainID,
	}

	// If address was pre-configured, use it
	if !config.Address.IsZero() {
		wallet.address = config.Address
	}

	return wallet, nil
}

// Type returns the wallet type identifier.
func (p *KMSWalletProvider) Type() string {
	return "kms"
}

// Open initializes the KMS wallet connection.
// In Phase 4, this validates connectivity to the KMS endpoint.
func (w *KMSWallet) Open(ctx context.Context) error {
	// Phase 4 stub: validate KMS connectivity
	// TODO(milestone-4): Implement AWS SDK KMS client initialization
	w.isOpen = true
	return nil
}

// Close releases the KMS wallet resources.
func (w *KMSWallet) Close() error {
	w.isOpen = false
	return nil
}

// Address returns the public address derived from the KMS key.
func (w *KMSWallet) Address() domain.Address {
	return w.address
}

// Chain returns the chain ID this wallet is associated with.
func (w *KMSWallet) Chain() domain.ChainID {
	return w.chainID
}

// Sign signs an unsigned transaction using the KMS key.
// Returns ErrNotOpen if the wallet is not open.
func (w *KMSWallet) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	if !w.isOpen {
		return domain.SignedTx{}, ErrNotOpen
	}

	_ = ctx
	_ = tx
	return domain.SignedTx{}, ErrNotImplemented
}

// ApproveExact returns an approval transaction for the exact amount.
// Phase 4 stub: returns ErrNotImplemented.
func (w *KMSWallet) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	if !w.isOpen {
		return domain.UnsignedTx{}, ErrNotOpen
	}
	return domain.UnsignedTx{}, ErrNotImplemented
}

// Revoke returns a revocation transaction to revoke token approval.
// Phase 4 stub: returns ErrNotImplemented.
func (w *KMSWallet) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	if !w.isOpen {
		return domain.UnsignedTx{}, ErrNotOpen
	}
	return domain.UnsignedTx{}, ErrNotImplemented
}
