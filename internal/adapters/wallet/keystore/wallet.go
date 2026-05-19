// Package keystore implements a keystore-based wallet adapter for lp-bot.
//
// This adapter provides transaction signing using encrypted keystore files
// (e.g., EVM keystore format used by geth, or similar for Solana).
//
// Phase 3 implementation will add:
//   - Encrypted keystore file parsing
//   - Passphrase-based decryption
//   - Transaction signing with derived private key
package keystore

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// wallet implements the ports.Wallet interface for keystore-based signing.
type wallet struct {
	// TODO (Phase 3): Add keystore state
	// This is a stub that implements the interface but does not actually sign.
	// - Loaded private key (decrypted from keystore)
	// - Chain configuration
}

// New creates a new keystore wallet instance.
//
// Configuration is adapter-specific and may include:
//   - KeystoreDir: path to keystore directory
//   - KeystoreFile: specific keystore file name
//   - Passphrase: optional passphrase (may be prompted interactively)
//   - ChainID: the chain this wallet operates on
func New(ctx context.Context, config ports.WalletConfig) (ports.Wallet, error) {
	// TODO (Phase 3): Validate configuration
	// - Check keystore directory exists
	// - Parse keystore file if specified
	return &wallet{}, nil
}

// Open initializes the wallet and decrypts the keystore.
//
// TODO (Phase 3): Implement keystore decryption
// - Load and parse keystore JSON file
// - Decrypt using passphrase
// - Validate derived address matches configured address
func (w *wallet) Open(ctx context.Context) error {
	// TODO (Phase 3): Implement keystore opening
	return nil
}

// Close releases the decrypted private key from memory.
func (w *wallet) Close() error {
	// TODO (Phase 3): Zero out private key memory
	return nil
}

// Address returns the public address of the wallet.
//
// Returns empty address if the wallet is not open.
func (w *wallet) Address() domain.Address {
	// TODO (Phase 3): Return actual address
	return domain.Address{}
}

// Chain returns the chain ID this wallet is associated with.
//
// Returns empty string if the wallet is not open.
func (w *wallet) Chain() domain.ChainID {
	// TODO (Phase 3): Return actual chain ID
	return ""
}

// Sign signs an unsigned transaction with the decrypted private key.
//
// TODO (Phase 3): Implement actual transaction signing
func (w *wallet) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	// TODO (Phase 3): Implement actual signing
	return domain.SignedTx{}, nil
}

// ApproveExact constructs an approval transaction for exact amount.
//
// TODO (Phase 3): Implement ERC20 approve for exact amount
func (w *wallet) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	// TODO (Phase 3): Implement approval transaction construction
	return domain.UnsignedTx{}, nil
}

// Revoke constructs a revocation transaction setting allowance to 0.
//
// TODO (Phase 3): Implement ERC20 approve(0) for revocation
func (w *wallet) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	// TODO (Phase 3): Implement revocation transaction construction
	return domain.UnsignedTx{}, nil
}