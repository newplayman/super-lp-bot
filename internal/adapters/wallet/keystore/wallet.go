// Package keystore implements a keystore-based wallet adapter for lp-bot.
//
// This adapter provides transaction signing using encrypted keystore files
// (ERC-155 style encryption used by geth).
package keystore

import (
	"context"
	"crypto/ecdsa"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"math/big"
	"os"
	"path/filepath"

	"github.com/ethereum/go-ethereum/accounts/keystore"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

var (
	ErrWalletNotOpen  = errors.New("wallet is not open")
	ErrNoPrivateKey   = errors.New("private key not available")
	ErrInvalidChainID = errors.New("invalid chain ID")
	ErrKeyMismatch    = errors.New("address does not match keystore")
	ErrNoRPCProvider = errors.New("RPC provider required for nonce queries")
)

// keystoreWallet implements ports.Wallet using an encrypted keystore file.
type keystoreWallet struct {
	key         *keystore.Key
	address     domain.Address
	chainID     domain.ChainID
	rpcProvider RPCProvider // For nonce queries
}

// RPCProvider interface for getting nonces
type RPCProvider interface {
	PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error)
}

// New creates a new keystore wallet provider.
func New(_ context.Context, config ports.WalletConfig) (*WalletProvider, error) {
	// Validate configuration
	if config.KeystoreDir == "" {
		return nil, errors.New("keystore directory is required")
	}

	// Check if directory exists
	if _, err := os.Stat(config.KeystoreDir); err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, fmt.Errorf("keystore directory does not exist: %s", config.KeystoreDir)
		}
		return nil, fmt.Errorf("failed to access keystore directory: %w", err)
	}

	provider := &WalletProvider{
		keyDir:     config.KeystoreDir,
		passphrase: config.Passphrase,
		chainID:    config.ChainID,
		address:    config.Address,
		keyFile:    config.KeystoreFile,
	}

	return provider, nil
}

// WalletProvider creates keystoreWallet instances.
type WalletProvider struct {
	keyDir     string
	keyFile    string
	passphrase string
	chainID    domain.ChainID
	address    domain.Address
	rpcProvider RPCProvider
}

// SetRPCProvider sets the RPC provider for nonce queries.
func (p *WalletProvider) SetRPCProvider(rpc RPCProvider) {
	p.rpcProvider = rpc
}

// Open creates a new keystoreWallet instance by loading and decrypting a keystore file.
func (p *WalletProvider) Open(_ context.Context, config ports.WalletConfig) (ports.Wallet, error) {
	// Create wallet with decrypted key
	wallet := &keystoreWallet{
		chainID:     p.chainID,
		rpcProvider: p.rpcProvider,
	}

	// Find keystore file
	keyFile := p.keyFile
	if keyFile == "" {
		// Find the first UTC keystore file in the directory
		// Pattern: UTC--<timestamp>--<address>
		files, err := os.ReadDir(p.keyDir)
		if err != nil {
			return nil, fmt.Errorf("failed to read keystore directory: %w", err)
		}
		for _, f := range files {
			if !f.IsDir() {
				// Check if file matches UTC keystore pattern
				name := f.Name()
				if len(name) >= 42 && name[:4] == "UTC-" {
					keyFile = name
					break
				}
			}
		}
		if keyFile == "" {
			return nil, errors.New("no keystore file found in directory")
		}
	}

	keyPath := filepath.Join(p.keyDir, keyFile)

	// Load and decrypt keystore
	keyJSON, err := os.ReadFile(keyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read keystore file: %w", err)
	}

	// Decrypt the key
	key, err := keystore.DecryptKey(keyJSON, p.passphrase)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt keystore: %w", err)
	}

	wallet.key = key
	wallet.address = domain.MustParseAddress(key.Address.Hex())

	// Validate address if configured
	if !p.address.IsZero() && string(wallet.address.Bytes()) != string(p.address.Bytes()) {
		return nil, ErrKeyMismatch
	}

	return wallet, nil
}

// Type returns the wallet provider type identifier.
func (p *WalletProvider) Type() string {
	return "keystore"
}

// Open initializes the wallet (no-op for keystore, already open after New).
func (w *keystoreWallet) Open(_ context.Context) error {
	// Already open after construction
	return nil
}

// Close securely clears the private key from memory.
func (w *keystoreWallet) Close() error {
	if w.key != nil && w.key.PrivateKey != nil {
		// Zero out the private key bytes
		priv := w.key.PrivateKey
		zero := make([]byte, len(priv.D.Bytes()))
		priv.D.SetBytes(zero)
		w.key = nil
	}
	return nil
}

// Address returns the public address of the wallet.
func (w *keystoreWallet) Address() domain.Address {
	return w.address
}

// Chain returns the chain ID this wallet is associated with.
func (w *keystoreWallet) Chain() domain.ChainID {
	return w.chainID
}

// Sign signs an unsigned transaction with the decrypted private key.
func (w *keystoreWallet) Sign(_ context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	if w.key == nil {
		return domain.SignedTx{}, ErrWalletNotOpen
	}

	// Get chain ID
	chainID, err := chainIDToBigInt(tx.Chain)
	if err != nil {
		return domain.SignedTx{}, err
	}

	// Convert to EVM transaction
	evmTx, err := w.buildEVMTransaction(tx, chainID)
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("failed to build EVM transaction: %w", err)
	}

	// Sign the transaction
	signer := types.LatestSignerForChainID(chainID)
	signedTx, err := types.SignTx(evmTx, signer, w.key.PrivateKey)
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("failed to sign transaction: %w", err)
	}

	// Encode to RLP
	signedBytes, err := signedTx.MarshalBinary()
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("failed to encode signed transaction: %w", err)
	}

	signedTxDomain := domain.SignedTx{
		UnsignedTx: tx,
		Signature:  signedBytes,
		Hash:       signedTx.Hash().Hex(),
	}

	return signedTxDomain, nil
}

// ApproveExact constructs an approval transaction for exact amount.
func (w *keystoreWallet) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	if w.key == nil {
		return domain.UnsignedTx{}, ErrWalletNotOpen
	}

	// ERC20 approve function signature: approve(address,uint256)
	// Function selector: 0x095ea7b3
	data := append(
		[]byte{0x09, 0x5e, 0xa7, 0xb3}, // approve selector
		common.LeftPadBytes(spender.Bytes(), 32)...,
	)
	data = append(data, common.LeftPadBytes(amount.Bytes(), 32)...)

	nonce, err := w.getNonce(ctx, token)
	if err != nil {
		return domain.UnsignedTx{}, fmt.Errorf("failed to get nonce: %w", err)
	}

	return domain.UnsignedTx{
		Chain:    w.chainID,
		From:     w.address,
		To:       token,
		Data:     data,
		Value:    domain.ZeroDecimal(),
		Nonce:    nonce,
		Deadline: 0, // Set by caller
		MinOut:   domain.ZeroDecimal(),
	}, nil
}

// Revoke constructs a revocation transaction setting allowance to 0.
func (w *keystoreWallet) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	return w.ApproveExact(ctx, token, spender, big.NewInt(0))
}

// buildEVMTransaction converts domain.UnsignedTx to types.Transaction.
func (w *keystoreWallet) buildEVMTransaction(tx domain.UnsignedTx, chainID *big.Int) (*types.Transaction, error) {
	value := tx.Value.BigInt()

	// Determine transaction type
	if tx.Data != nil && len(tx.Data) > 0 {
		// Check if it's a contract creation (no To address)
		if tx.To.IsZero() {
			return types.NewContractCreation(
				tx.Nonce,
				value,
				0, // gasLimit - caller should estimate
				big.NewInt(0),
				tx.Data,
			), nil
		}
		// Contract call
		return types.NewTransaction(
			tx.Nonce,
			common.HexToAddress(tx.To.String()),
			value,
			0, // gasLimit - caller should estimate
			big.NewInt(0),
			tx.Data,
		), nil
	}

	// Regular transfer
	return types.NewTransaction(
		tx.Nonce,
		common.HexToAddress(tx.To.String()),
		value,
		0,
		big.NewInt(0),
		nil,
	), nil
}

// getNonce returns the next nonce for the given address.
// Uses the RPC provider to query the blockchain for the actual nonce.
func (w *keystoreWallet) getNonce(ctx context.Context, addr domain.Address) (uint64, error) {
	if w.rpcProvider == nil {
		return 0, ErrNoRPCProvider
	}
	return w.rpcProvider.PendingNonceAt(ctx, addr)
}

// chainIDToBigInt converts domain.ChainID to *big.Int.
// Only supports EVM chains (base, solana in domain, but we support EVM chains here).
func chainIDToBigInt(chainID domain.ChainID) (*big.Int, error) {
	switch chainID {
	case domain.ChainBase:
		return big.NewInt(8453), nil
	case domain.ChainSolana:
		return nil, ErrInvalidChainID
	default:
		return nil, fmt.Errorf("%w: %s", ErrInvalidChainID, chainID)
	}
}

// ExportKey exports the decrypted key as JSON for backup.
// SECURITY WARNING: This exposes the private key - use with extreme caution.
func (w *keystoreWallet) ExportKey() ([]byte, error) {
	if w.key == nil {
		return nil, ErrWalletNotOpen
	}

	return json.Marshal(w.key)
}

// PrivateKey returns the underlying private key.
// SECURITY WARNING: This exposes the private key - use with extreme caution.
func (w *keystoreWallet) PrivateKey() *ecdsa.PrivateKey {
	if w.key == nil {
		return nil
	}
	return w.key.PrivateKey
}

// PublicKey returns the underlying public key.
func (w *keystoreWallet) PublicKey() *ecdsa.PublicKey {
	if w.key == nil {
		return nil
	}
	return &w.key.PrivateKey.PublicKey
}

// SignMessage signs a message and returns the signature.
func (w *keystoreWallet) SignMessage(_ context.Context, message []byte) ([]byte, error) {
	if w.key == nil {
		return nil, ErrWalletNotOpen
	}

	// Sign the message hash (EIP-191 style)
	hash := crypto.Keccak256Hash(message)
	sig, err := crypto.Sign(hash.Bytes(), w.key.PrivateKey)
	if err != nil {
		return nil, fmt.Errorf("failed to sign message: %w", err)
	}

	return sig, nil
}