// Package execution implements the OrderManager pattern for transaction execution.
// It orchestrates the full lifecycle from approved position intents to confirmed
// on-chain transactions.
package execution

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// NonceManagerForReorg defines the interface for nonce management used by reorg handler.
type NonceManagerForReorg interface {
	GetNextNonce(ctx context.Context) (uint64, error)
	ClearPending(nonce uint64)
}

// ErrTxNotTracked is returned when a transaction is not tracked for reorg.
var ErrTxNotTracked = errors.New("tx not tracked for reorg")

// ErrReorgDetected is returned when a reorganization is detected.
var ErrReorgDetected = errors.New("reorg detected")

// ErrReorgMaxRetries is returned when max reorg retries are exceeded.
var ErrReorgMaxRetries = errors.New("max reorg retries exceeded")

// MaxReorgRetries is the maximum number of reorg recovery attempts.
const MaxReorgRetries = 3

// txReorgState tracks transaction state during reorg handling.
type txReorgState struct {
	OriginalBlock domain.BlockRef
	Nonce         uint64
	RawTx         []byte
	Attempts      int
}

// reorgHandler detects chain reorganizations and handles recovery.
// It monitors block hashes, detects when transactions are reorged out,
// rolls back position state, and re-broadcasts transactions with new nonces.
type reorgHandler struct {
	chain       ports.EVMChain
	txRepo      ports.TxRepo
	broadcaster ports.Broadcaster
	bus         ports.Bus
	nonceMgr    NonceManagerForReorg
	txStates    map[string]*txReorgState // txHash -> state
	mu          sync.RWMutex
}

// ReorgDependencies contains the dependencies for the reorg handler.
type ReorgDependencies struct {
	Chain       ports.EVMChain
	TxRepo      ports.TxRepo
	Broadcaster ports.Broadcaster
	Bus         ports.Bus
	NonceMgr    NonceManagerForReorg
}

// NewReorgHandler creates a new reorg handler.
func NewReorgHandler(deps ReorgDependencies) *reorgHandler {
	return &reorgHandler{
		chain:       deps.Chain,
		txRepo:      deps.TxRepo,
		broadcaster: deps.Broadcaster,
		bus:         deps.Bus,
		nonceMgr:    deps.NonceMgr,
		txStates:    make(map[string]*txReorgState),
	}
}

// Compile-time interface assertion.
var _ interface {
	BlockMonitor
	ReorgDetector
	ReorgHandler
	ReorgRecorder
} = (*reorgHandler)(nil)

// BlockMonitor is the interface for monitoring blocks.
type BlockMonitor interface {
	MonitorBlock(ctx context.Context, blockHash string) (bool, error)
}

// ReorgDetector is the interface for detecting reorgs.
type ReorgDetector interface {
	DetectReorg(ctx context.Context, txHash string) (bool, error)
}

// ReorgHandler is the interface for handling reorgs.
type ReorgHandler interface {
	HandleReorg(ctx context.Context, txHash string) error
}

// ReorgRecorder is the interface for recording reorg events.
type ReorgRecorder interface {
	RecordReorgEvent(ctx context.Context, txHash string, reason string) error
}

// MonitorBlock checks if a block hash has changed from what was recorded.
// This is used to detect potential chain reorganizations by comparing
// the current block hash against the expected hash.
//
// Returns true if the block hash changed (reorg detected), false otherwise.
// Returns an error if the check fails.
func (h *reorgHandler) MonitorBlock(ctx context.Context, blockHash string) (bool, error) {
	h.mu.RLock()
	state, exists := h.getTxStateByBlockHash(blockHash)
	h.mu.RUnlock()

	if !exists {
		// No transaction was confirmed in this block
		return false, nil
	}

	// Check if the block hash has changed on chain
	currentBlock, err := h.chain.GetBlock(ctx, state.OriginalBlock)
	if err != nil {
		return false, err
	}

	// If hash is different, a reorg occurred
	if currentBlock.Ref.Hash != state.OriginalBlock.Hash {
		return true, nil
	}

	return false, nil
}

// DetectReorg detects if a transaction was reorged out of the chain.
// It checks if the transaction's block no longer contains it or if
// the block hash has changed.
//
// Returns true if reorg detected, false otherwise.
// Returns an error if detection fails.
func (h *reorgHandler) DetectReorg(ctx context.Context, txHash string) (bool, error) {
	h.mu.RLock()
	state, exists := h.txStates[txHash]
	h.mu.RUnlock()

	if !exists {
		return false, ErrTxNotTracked
	}

	// Try to get the transaction receipt from chain
	// If the tx is not found in the expected block, it was reorged
	block, err := h.chain.GetBlock(ctx, state.OriginalBlock)
	if err != nil {
		return false, err
	}

	// If block hash changed, reorg occurred
	if block.Ref.Hash != state.OriginalBlock.Hash {
		return true, nil
	}

	return false, nil
}

// HandleReorg handles a detected reorg by:
// 1. Rolling back position state if needed
// 2. Getting a new nonce
// 3. Re-broadcasting the transaction
//
// Returns an error if handling fails or max retries exceeded.
func (h *reorgHandler) HandleReorg(ctx context.Context, txHash string) error {
	h.mu.Lock()
	state, exists := h.txStates[txHash]
	if !exists {
		h.mu.Unlock()
		return ErrTxNotTracked
	}

	// Check retry limit
	if state.Attempts >= MaxReorgRetries {
		h.mu.Unlock()
		return ErrReorgMaxRetries
	}

	// Increment attempt counter
	state.Attempts++
	h.mu.Unlock()

	// Update tx status in store to reorged
	tx, err := h.txRepo.GetTxByHash(ctx, h.chain.Info().ID, txHash)
	if err != nil {
		return err
	}

	// Mark transaction as reorged
	if err := h.txRepo.UpdateTxStatus(ctx, h.chain.Info().ID, txHash, domain.TxReorged, nil); err != nil {
		return err
	}

	// Clear the old nonce from tracking
	h.nonceMgr.ClearPending(state.Nonce)

	// Get new nonce for re-broadcast
	newNonce, err := h.nonceMgr.GetNextNonce(ctx)
	if err != nil {
		return err
	}

	// Create new signed tx with new nonce
	newTx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			Chain:  tx.Chain,
			From:   tx.From,
			To:     tx.To,
			Data:   state.RawTx,
			Value:  tx.Value,
			Nonce:  newNonce,
		},
		Signature: tx.Signature,
	}

	// Re-broadcast
	if err := h.broadcaster.Send(ctx, newTx); err != nil {
		return err
	}

	// Update status to broadcast
	if err := h.txRepo.UpdateTxStatus(ctx, h.chain.Info().ID, newTx.Hash, domain.TxBroadcast, nil); err != nil {
		return err
	}

	// Update tracked state with new tx hash
	h.mu.Lock()
	h.txStates[newTx.Hash] = &txReorgState{
		OriginalBlock: state.OriginalBlock,
		Nonce:         newNonce,
		RawTx:         state.RawTx,
		Attempts:      state.Attempts,
	}
	// Remove old tx hash tracking
	delete(h.txStates, txHash)
	h.mu.Unlock()

	// Record reorg event
	h.RecordReorgEvent(ctx, txHash, "reorg detected, tx rebroadcast")

	return nil
}

// RecordReorgEvent records a reorg event for audit purposes.
// It publishes a reorg event on the bus for downstream consumers.
func (h *reorgHandler) RecordReorgEvent(ctx context.Context, txHash string, reason string) error {
	// Get current time for timestamp
	timestamp := time.Now().UnixNano()

	// Create audit payload
	payload := ReorgAuditPayload{
		TxHash:    txHash,
		Reason:    reason,
		Timestamp: timestamp,
		Chain:     h.chain.Info().ID,
	}

	// Create and publish event
	event, err := domain.NewEvent("live.reorg.detected", domain.EnvLive, payload)
	if err != nil {
		return err
	}

	event.Timestamp = timestamp

	return h.bus.Publish(event)
}

// TrackTransaction starts tracking a transaction for reorg detection.
func (h *reorgHandler) TrackTransaction(txHash string, block domain.BlockRef, nonce uint64, rawTx []byte) {
	h.mu.Lock()
	defer h.mu.Unlock()

	h.txStates[txHash] = &txReorgState{
		OriginalBlock: block,
		Nonce:         nonce,
		RawTx:         rawTx,
		Attempts:      0,
	}
}

// UntrackTransaction removes a transaction from reorg tracking.
func (h *reorgHandler) UntrackTransaction(txHash string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	delete(h.txStates, txHash)
}

// GetReorgState returns the reorg state for a transaction.
func (h *reorgHandler) GetReorgState(txHash string) (*txReorgState, bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	state, exists := h.txStates[txHash]
	return state, exists
}

// getTxStateByBlockHash looks up a transaction state by block hash.
func (h *reorgHandler) getTxStateByBlockHash(blockHash string) (*txReorgState, bool) {
	for _, state := range h.txStates {
		if state.OriginalBlock.Hash == blockHash {
			return state, true
		}
	}
	return nil, false
}

// ReorgAuditPayload is the payload for reorg audit events.
type ReorgAuditPayload struct {
	TxHash    string        `json:"tx_hash"`
	Reason    string        `json:"reason"`
	Timestamp int64         `json:"timestamp"`
	Chain     domain.ChainID `json:"chain"`
}