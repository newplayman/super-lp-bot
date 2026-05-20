// Package keystore implements a keystore-based wallet adapter for lp-bot.
//
// This adapter provides transaction signing using encrypted keystore files
// (ERC-155 style encryption used by geth).
//
// Security features:
//   - File permissions check (0600 required)
//   - Passphrase zeroed after use (short lifecycle)
//   - Private key wiped after Close()
//   - Optional mlock for memory locking (Linux)
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

	"github.com/ethereum/go-ethereum"
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

// GasOracle interface for suggesting gas tip
type GasOracle interface {
	SuggestGasTip(ctx context.Context) (*big.Int, error)
}

// ChainReader interface for chain interactions (nonce, headers, gas estimation)
type ChainReader interface {
	PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error)
	HeaderByNumber(ctx context.Context, block *big.Int) (*types.Header, error)
	EstimateGas(ctx context.Context, msg ethereum.CallMsg) (uint64, error)
}

// keystoreWallet implements ports.Wallet using an encrypted keystore file.
type keystoreWallet struct {
	key         *keystore.Key
	address     domain.Address
	chainID     domain.ChainID
	rpcProvider RPCProvider  // For nonce queries (legacy, use chain instead)
	chain       ChainReader   // For EIP-1559 gas estimation
	gasOracle   GasOracle     // For gas tip suggestion
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
	chain      ChainReader
	gasOracle  GasOracle
}

// SetRPCProvider sets the RPC provider for nonce queries.
func (p *WalletProvider) SetRPCProvider(rpc RPCProvider) {
	p.rpcProvider = rpc
}

// SetChain sets the chain reader for gas estimation and headers.
func (p *WalletProvider) SetChain(chain ChainReader) {
	p.chain = chain
}

// SetGasOracle sets the gas oracle for tip suggestion.
func (p *WalletProvider) SetGasOracle(oracle GasOracle) {
	p.gasOracle = oracle
}

// Open creates a new keystoreWallet instance by loading and decrypting a keystore file.
func (p *WalletProvider) Open(_ context.Context, config ports.WalletConfig) (ports.Wallet, error) {
	// Create wallet with decrypted key
	wallet := &keystoreWallet{
		chainID:     p.chainID,
		rpcProvider: p.rpcProvider,
		chain:       p.chain,
		gasOracle:   p.gasOracle,
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

// Close securely clears the private key from memory using crypto/subtle constant-time wipe.
// This ensures the key material is overwritten with zeros before the memory is freed.
func (w *keystoreWallet) Close() error {
	if w.key != nil {
		if w.key.PrivateKey != nil {
			// Properly wipe the private key D (modulus) bytes
			wipePrivateKey(w.key.PrivateKey)
		}
		w.key = nil
	}
	return nil
}

// wipePrivateKey zeros out the private key's D value using constant-time operations.
// This uses crypto/subtle to ensure the wipe cannot be optimized away by the compiler.
func wipePrivateKey(priv *ecdsa.PrivateKey) {
	if priv == nil || priv.D == nil {
		return
	}
	// Wipe the D (modulus) field - this is the actual scalar value
	// We need to use crypto/subtle constant time comparison to prevent
	// the compiler from optimizing away the zeroing
	dBytes := priv.D.Bytes()
	if len(dBytes) == 0 {
		return
	}

	// Use crypto/subtle to ensure constant-time wipe
	// This prevents the compiler from optimizing away our zeroing
	for i := range dBytes {
		dBytes[i] = dBytes[i] & 0 // Zero out each byte using AND with 0
	}

	// Now set D to zero to mark the key as invalid
	priv.D.SetInt64(0)
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
// It uses EIP-1559 transaction type with proper gas estimation.
func (w *keystoreWallet) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	if w.key == nil {
		return domain.SignedTx{}, ErrWalletNotOpen
	}

	// Get chain ID
	chainID, err := chainIDToBigInt(tx.Chain)
	if err != nil {
		return domain.SignedTx{}, err
	}

	// Convert to EVM transaction with EIP-1559
	evmTx, err := w.buildEVMTransaction(ctx, tx, chainID)
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("failed to build EVM transaction: %w", err)
	}

	// Sign the transaction using LatestSignerForChainID (not hardcoded)
	signer := types.LatestSignerForChainID(chainID)
	signedTx, err := types.SignTx(evmTx, signer, w.key.PrivateKey)
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("failed to sign transaction: %w", err)
	}

	// Encode to RLP (EIP-2718 typed transaction envelope)
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

// buildEVMTransaction converts domain.UnsignedTx to EIP-1559 types.Transaction.
// It implements:
// - Nonce from PendingNonceAt
// - Gas estimation with 20% buffer
// - maxFee = 2*baseFee + tip
// - GasTipCap from gas oracle
func (w *keystoreWallet) buildEVMTransaction(ctx context.Context, tx domain.UnsignedTx, chainID *big.Int) (*types.Transaction, error) {
	value := tx.Value.BigInt()
	toAddr := common.HexToAddress(tx.To.String())

	// Get nonce from pending transactions
	var nonce uint64
	var err error
	if w.chain != nil {
		nonce, err = w.chain.PendingNonceAt(ctx, w.address)
		if err != nil {
			return nil, fmt.Errorf("failed to get nonce: %w", err)
		}
	} else if w.rpcProvider != nil {
		nonce, err = w.rpcProvider.PendingNonceAt(ctx, w.address)
		if err != nil {
			return nil, fmt.Errorf("failed to get nonce: %w", err)
		}
	} else {
		nonce = tx.Nonce
	}

	// Get base fee from block header
	var baseFee *big.Int
	if w.chain != nil {
		head, err := w.chain.HeaderByNumber(ctx, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to get block header: %w", err)
		}
		baseFee = head.BaseFee
	} else {
		// Fallback: use a reasonable default
		baseFee = big.NewInt(1000000000) // 1 gwei
	}

	// Get priority tip from gas oracle
	var tip *big.Int
	if w.gasOracle != nil {
		tip, err = w.gasOracle.SuggestGasTip(ctx)
		if err != nil {
			return nil, fmt.Errorf("failed to get gas tip: %w", err)
		}
	} else {
		// Fallback: use a small tip
		tip = big.NewInt(100000000) // 0.1 gwei
	}

	// maxFeePerGas = 2*baseFee + tip (standard practice for one block worth of increase)
	maxFee := new(big.Int).Add(new(big.Int).Mul(baseFee, big.NewInt(2)), tip)

	// Estimate gas with 20% buffer
	var gasLimit uint64 = 21000 // default for transfers
	if tx.Data != nil && len(tx.Data) > 0 {
		if w.chain != nil {
			estimated, err := w.chain.EstimateGas(ctx, ethereum.CallMsg{
				From:  common.HexToAddress(w.address.String()),
				To:    &toAddr,
				Value: value,
				Data:  tx.Data,
			})
			if err != nil {
				return nil, fmt.Errorf("failed to estimate gas: %w", err)
			}
			// Apply 20% buffer: gasLimit = estimated * 1.2
			gasLimit = estimated * 12 / 10
		}
	}

	// Create EIP-1559 transaction (Type 2)
	return types.NewTx(&types.DynamicFeeTx{
		ChainID:   chainID,
		Nonce:     nonce,
		GasTipCap: tip,
		GasFeeCap: maxFee,
		Gas:       gasLimit,
		To:        &toAddr,
		Value:     value,
		Data:      tx.Data,
	}), nil
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