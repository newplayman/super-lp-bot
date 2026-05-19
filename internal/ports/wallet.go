// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// Wallet interfaces (this file):
//
//   - Wallet: transaction signing and approval management
//   - WalletProvider: factory for creating Wallet instances
//
// See spec §6 (table row: Wallet + WalletProvider) and invariant #9/#10.
package ports

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
)

// Wallet defines the interface for wallet operations including transaction signing
// and token approval management. Implementations must be safe for concurrent use.
//
// Wallet responsibilities (spec §6.8, invariants #9 and #10):
//
//   - Sign unsigned transactions with the wallet's private key
//   - ApproveExact: approve only the exact amount needed (no ApproveMax)
//   - Revoke: revoke previously granted token approvals
//   - Open: unlock/initialize the wallet for use
//
// Implementations should never hold private key material in memory longer than
// necessary; use hardware security modules or secure enclaves where possible.
type Wallet interface {
	// Open initializes the wallet and prepares it for signing operations.
	// The behavior depends on the underlying implementation:
	//
	//   - keystore: prompts for passphrase or reads from encrypted file
	//   - KMS: authenticates with the KMS service
	//   - none: returns nil (dryrun/shadow modes)
	//
	// Open must be called before any Sign or Approve operations.
	// Implementations may require Open to be called after a period of inactivity.
	Open(ctx context.Context) error

	// Close releases any resources held by the wallet (e.g., closed sessions,
	// released key references). After Close, subsequent Sign/Approve calls
	// should fail until Open is called again.
	Close() error

	// Address returns the public address of the wallet.
	// Returns an empty Address if the wallet is not open.
	Address() domain.Address

	// Chain returns the chain ID this wallet is associated with.
	// Returns empty string if the wallet is not open.
	Chain() domain.ChainID

	// Sign signs an unsigned transaction with the wallet's private key.
	// The transaction must have its Chain, From, To, Data, Value, Nonce, Deadline,
	// and MinOut fields populated (invariant #4: MinOut and Deadline must be non-zero).
	//
	// Returns a SignedTx with the signature populated.
	// Returns an error if:
	//   - the wallet is not open
	//   - signing fails (e.g., insufficient key material, cryptographic failure)
	//   - the transaction is invalid
	//
	// Sign does NOT broadcast the transaction; use Broadcaster for that.
	Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error)

	// ApproveExact grants approval for a spender to transfer tokens from the wallet.
	// Unlike ApproveMax (which is not part of this interface, per invariant #9),
	// ApproveExact approves only the exact amount needed.
	//
	// Parameters:
	//   - token: the token address to approve
	//   - spender: the address that will be allowed to spend tokens
	//   - amount: the exact number of tokens to approve (must be > 0)
	//
	// Returns an unsigned transaction to approve, or an error if:
	//   - the wallet is not open
	//   - amount is zero or negative
	//   - the approval transaction cannot be constructed
	//
	// The caller is responsible for signing and broadcasting the returned transaction.
	// After the approval is confirmed on-chain, the spender can transfer up to amount.
	ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error)

	// Revoke revokes a previously granted token approval, setting the allowance to 0.
	//
	// Parameters:
	//   - token: the token address whose approval to revoke
	//   - spender: the address whose approval to revoke
	//
	// Returns an unsigned transaction to revoke approval, or an error if:
	//   - the wallet is not open
	//   - the revocation transaction cannot be constructed
	//
	// The caller is responsible for signing and broadcasting the returned transaction.
	// After the revocation is confirmed on-chain, the spender can no longer transfer tokens.
	//
	// This operation implements invariant #10: position exit must revoke token approvals.
	Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error)
}

// WalletProvider is a factory interface for creating Wallet instances.
//
// WalletProviders are used at application startup to create wallet instances
// based on configuration. Each wallet instance is independent and can be
// opened/closed separately.
//
// Usage pattern:
//
//	config := loadWalletConfig()
//	provider := NewKeystoreWalletProvider(config) // or NewKMSWalletProvider, NewNoneWalletProvider
//	wallet, err := provider.Open(ctx, config)
//	if err != nil { return err }
//	defer wallet.Close()
//
// Implementations should validate configuration at construction time,
// deferring resource allocation (e.g., file handles, network connections)
// until Open is called.
type WalletProvider interface {
	// Open creates a new Wallet instance using the provided configuration.
	//
	// The config parameter is adapter-specific:
	//   - keystore: path to keystore directory, optional passphrase
	//   - KMS: KMS key ID and region/endpoint
	//   - none: ignored (returns a no-op wallet)
	//
	// Returns a Wallet instance ready to use after Open is called on it,
	// or an error if configuration is invalid.
	//
	// The returned Wallet is not automatically opened; call wallet.Open(ctx)
	// before performing signing operations.
	Open(ctx context.Context, config WalletConfig) (Wallet, error)

	// Type returns the type identifier for this wallet provider.
	// This is used for logging, metrics, and error messages.
	//
	// Expected values:
	//   - "keystore": encrypted file-based wallet
	//   - "kms": AWS KMS or similar hardware security module
	//   - "none": no-op wallet for dryrun/shadow modes
	Type() string
}

// WalletConfig holds configuration for creating a Wallet instance.
// The interpretation of fields depends on the WalletProvider implementation.
type WalletConfig struct {
	// Type identifies the wallet type (used by the provider router).
	// Valid values: "keystore", "kms", "none"
	Type string

	// ChainID is the chain this wallet operates on (e.g., "base", "solana").
	ChainID domain.ChainID

	// Keystore fields (used when Type == "keystore")
	KeystoreDir  string
	KeystoreFile string
	Passphrase   string

	// KMS fields (used when Type == "kms")
	KMSKeyID     string
	KMSRegion    string
	KMSEndpoint  string
	KMSKeyAlias  string

	// Common fields
	Address domain.Address
}