//go:build live

// Package live implements the live broadcast adapter for lp-bot.
//
// This adapter is only compiled in live builds (go build -tags live).
// In live builds, transactions are actually broadcast to the network.
//
// In non-live builds (dryrun/shadow), use adapters/broadcast/disabled instead.
package live

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync/atomic"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/ethclient"

	"github.com/gagliardetto/solana-go"
	"github.com/gagliardetto/solana-go/rpc"
	bin "github.com/gagliardetto/binary"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Compile-time interface assertion
var _ ports.Broadcaster = (*broadcaster)(nil)

// Receipt represents a transaction receipt.
type Receipt struct {
	TxHash      string
	BlockNumber uint64
	BlockHash   string
	Success     bool
	GasUsed     uint64
}

// BroadcastConfig holds the configuration for the live broadcaster.
type BroadcastConfig struct {
	BaseRPCURL          string
	SolanaRPCURL        string
	Confirmations       int // Number of confirmations to wait for before returning success
	SolanaSkipPreflight bool
}

// broadcaster implements ports.Broadcaster for live broadcast.
type broadcaster struct {
	ethClient           *ethclient.Client
	solClient           *rpc.Client
	confirmations       int
	solanaSkipPreflight bool
	callCount           int64
}

// New creates a new live broadcaster instance.
func New(_ context.Context, config BroadcastConfig) (ports.Broadcaster, error) {
	if config.BaseRPCURL == "" {
		return nil, errors.New("BaseRPCURL is required for live broadcast")
	}

	// Create Ethereum RPC client
	ethClient, err := ethclient.Dial(config.BaseRPCURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to Base RPC: %w", err)
	}

	// Create Solana RPC client
	solClient := rpc.New(config.SolanaRPCURL)

	b := &broadcaster{
		ethClient:           ethClient,
		solClient:           solClient,
		confirmations:       config.Confirmations,
		solanaSkipPreflight: config.SolanaSkipPreflight,
	}

	return b, nil
}

// Send broadcasts a signed transaction to the network.
func (b *broadcaster) Send(ctx context.Context, tx domain.SignedTx) error {
	atomic.AddInt64(&b.callCount, 1)

	switch tx.Chain {
	case domain.ChainBase:
		return b.sendEVM(ctx, tx)
	case domain.ChainSolana:
		return b.sendSolana(ctx, tx)
	default:
		return fmt.Errorf("unsupported chain: %s", tx.Chain)
	}
}

// CallCount returns the number of times Send has been called.
func (b *broadcaster) CallCount() int64 {
	return atomic.LoadInt64(&b.callCount)
}

// sendEVM broadcasts a signed transaction to an EVM chain (Base).
func (b *broadcaster) sendEVM(ctx context.Context, tx domain.SignedTx) error {
	// Decode the signed transaction
	var evmTx types.Transaction
	if err := evmTx.UnmarshalBinary(tx.Signature); err != nil {
		return fmt.Errorf("failed to decode signed transaction: %w", err)
	}

	// Broadcast via eth_sendRawTransaction
	if err := b.ethClient.SendTransaction(ctx, &evmTx); err != nil {
		return fmt.Errorf("failed to broadcast transaction: %w", err)
	}

	// Wait for confirmations
	if b.confirmations > 0 {
		txHash := evmTx.Hash()
		if err := b.waitForEVMConfirmations(ctx, txHash); err != nil {
			return fmt.Errorf("failed to wait for confirmations: %w", err)
		}
	}

	return nil
}

// waitForEVMConfirmations waits for the transaction to be confirmed.
func (b *broadcaster) waitForEVMConfirmations(ctx context.Context, txHash common.Hash) error {
	// Wait for the transaction receipt
	confirmationTimeout := 120 * time.Second
	deadline := time.Now().Add(confirmationTimeout)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}

		if time.Now().After(deadline) {
			return errors.New("confirmation timeout")
		}

		receipt, err := b.ethClient.TransactionReceipt(ctx, txHash)
		if err != nil {
			if !errors.Is(err, ethereum.NotFound) {
				return fmt.Errorf("failed to get receipt: %w", err)
			}
			continue
		}

		// Check if we have enough confirmations
		if receipt.BlockNumber != nil {
			currentBlock, err := b.ethClient.BlockNumber(ctx)
			if err != nil {
				continue
			}

			if currentBlock >= receipt.BlockNumber.Uint64()+uint64(b.confirmations) {
				return nil
			}
		}
	}
}

// sendSolana broadcasts a signed transaction to Solana.
func (b *broadcaster) sendSolana(ctx context.Context, tx domain.SignedTx) error {
	// Decode the signed transaction
	var solTx solana.Transaction
	if err := solTx.UnmarshalWithDecoder(bin.NewBinDecoder(tx.Signature)); err != nil {
		return fmt.Errorf("failed to decode Solana transaction: %w", err)
	}

	// Broadcast via sendTransaction
	result, err := b.solClient.SendTransactionWithOpts(
		ctx,
		&solTx,
		rpc.TransactionOpts{
			SkipPreflight: b.solanaSkipPreflight,
		},
	)
	if err != nil {
		// Check for specific Solana RPC errors
		if strings.Contains(err.Error(), "already processed") {
			// Transaction already confirmed, not an error
			return nil
		}
		return fmt.Errorf("failed to broadcast Solana transaction: %w", err)
	}

	// Wait for confirmations
	if b.confirmations > 0 {
		if err := b.waitForSolanaConfirmations(ctx, result); err != nil {
			return fmt.Errorf("failed to wait for Solana confirmations: %w", err)
		}
	}

	return nil
}

// waitForSolanaConfirmations waits for the Solana transaction to be confirmed.
func (b *broadcaster) waitForSolanaConfirmations(ctx context.Context, txHash solana.Signature) error {
	confirmationTimeout := 120 * time.Second
	deadline := time.Now().Add(confirmationTimeout)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}

		if time.Now().After(deadline) {
			return errors.New("Solana confirmation timeout")
		}

		// Check transaction status
		result, err := b.solClient.GetSignatureStatuses(
			ctx,
			true, // searchTransactionHistory
			txHash,
		)
		if err != nil {
			continue
		}

		if len(result.Value) > 0 && result.Value[0] != nil {
			status := result.Value[0].ConfirmationStatus
			if status == rpc.ConfirmationStatusConfirmed || status == rpc.ConfirmationStatusFinalized {
				return nil
			}
		}
	}
}

// Broadcast broadcasts a signed transaction and returns the transaction hash.
// This is an alternative API that returns the tx hash.
func (b *broadcaster) Broadcast(ctx context.Context, signedTx []byte, chain domain.ChainID) (string, error) {
	atomic.AddInt64(&b.callCount, 1)

	switch chain {
	case domain.ChainBase:
		return b.broadcastEVM(ctx, signedTx)
	case domain.ChainSolana:
		return b.broadcastSolana(ctx, signedTx)
	default:
		return "", fmt.Errorf("unsupported chain: %s", chain)
	}
}

// broadcastEVM broadcasts to an EVM chain and returns the tx hash.
func (b *broadcaster) broadcastEVM(ctx context.Context, signedTx []byte) (string, error) {
	// Decode the signed transaction
	var evmTx types.Transaction
	if err := evmTx.UnmarshalBinary(signedTx); err != nil {
		return "", fmt.Errorf("failed to decode signed transaction: %w", err)
	}

	// Broadcast via eth_sendRawTransaction
	if err := b.ethClient.SendTransaction(ctx, &evmTx); err != nil {
		return "", fmt.Errorf("failed to broadcast EVM transaction: %w", err)
	}

	txHash := evmTx.Hash()

	// Wait for confirmations
	if b.confirmations > 0 {
		if err := b.waitForEVMConfirmations(ctx, txHash); err != nil {
			return txHash.String(), fmt.Errorf("failed to wait for confirmations: %w", err)
		}
	}

	return txHash.String(), nil
}

// broadcastSolana broadcasts to Solana and returns the tx hash.
func (b *broadcaster) broadcastSolana(ctx context.Context, signedTx []byte) (string, error) {
	var solTx solana.Transaction
	if err := solTx.UnmarshalWithDecoder(bin.NewBinDecoder(signedTx)); err != nil {
		return "", fmt.Errorf("failed to decode Solana transaction: %w", err)
	}

	result, err := b.solClient.SendTransactionWithOpts(
		ctx,
		&solTx,
		rpc.TransactionOpts{
			SkipPreflight: b.solanaSkipPreflight,
		},
	)
	if err != nil {
		if strings.Contains(err.Error(), "already processed") {
			return "", nil
		}
		return "", fmt.Errorf("failed to broadcast Solana transaction: %w", err)
	}

	// Wait for confirmations
	if b.confirmations > 0 {
		if err := b.waitForSolanaConfirmations(ctx, result); err != nil {
			return result.String(), fmt.Errorf("failed to wait for Solana confirmations: %w", err)
		}
	}

	return result.String(), nil
}

// GetTransactionReceipt retrieves the receipt for a broadcast transaction.
func (b *broadcaster) GetTransactionReceipt(ctx context.Context, txHash string, chain domain.ChainID) (*Receipt, error) {
	switch chain {
	case domain.ChainBase:
		return b.getEVMReceipt(ctx, txHash)
	case domain.ChainSolana:
		return b.getSolanaReceipt(ctx, txHash)
	default:
		return nil, fmt.Errorf("unsupported chain: %s", chain)
	}
}

// getEVMReceipt retrieves the receipt for an EVM transaction.
func (b *broadcaster) getEVMReceipt(ctx context.Context, txHash string) (*Receipt, error) {
	hash := common.HexToHash(txHash)
	receipt, err := b.ethClient.TransactionReceipt(ctx, hash)
	if err != nil {
		if errors.Is(err, ethereum.NotFound) {
			return nil, fmt.Errorf("transaction not found: %s", txHash)
		}
		return nil, fmt.Errorf("failed to get receipt: %w", err)
	}

	return &Receipt{
		TxHash:      receipt.TxHash.Hex(),
		BlockNumber: receipt.BlockNumber.Uint64(),
		BlockHash:   receipt.BlockHash.Hex(),
		Success:     receipt.Status == types.ReceiptStatusSuccessful,
		GasUsed:     receipt.GasUsed,
	}, nil
}

// getSolanaReceipt retrieves the receipt for a Solana transaction.
func (b *broadcaster) getSolanaReceipt(ctx context.Context, txHash string) (*Receipt, error) {
	sig, err := solana.SignatureFromBase58(txHash)
	if err != nil {
		return nil, fmt.Errorf("invalid signature: %s", txHash)
	}

	result, err := b.solClient.GetSignatureStatuses(ctx, true, sig)
	if err != nil {
		return nil, fmt.Errorf("failed to get Solana signature status: %w", err)
	}

	if len(result.Value) == 0 || result.Value[0] == nil {
		return nil, fmt.Errorf("transaction not found: %s", txHash)
	}

	status := result.Value[0]
	return &Receipt{
		TxHash:      txHash,
		BlockNumber: status.Slot,
		Success:     status.Err == nil,
	}, nil
}
