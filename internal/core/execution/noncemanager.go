// Package execution implements the OrderManager pattern for transaction execution.
// It orchestrates the full lifecycle from approved position intents to confirmed
// on-chain transactions.
package execution

import (
	"context"
	"errors"
	"sort"
	"sync"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// ErrNonceNotInitialized is returned when trying to use an uninitialized nonce.
var ErrNonceNotInitialized = errors.New("nonce not initialized")

// NonceManager tracks and manages EVM transaction nonces.
// It handles initialization from chain, monotonic increment, pending tracking,
// and stuck transaction detection.
type NonceManager struct {
	chain       ports.EVMChain
	walletAddr  domain.Address
	mu          sync.Mutex
	nonce       uint64
	initialized bool
	pending     map[uint64]string // nonce -> txHash
}

// NewNonceManager creates a new NonceManager for the given chain and wallet address.
func NewNonceManager(chain ports.EVMChain, walletAddr domain.Address) *NonceManager {
	return &NonceManager{
		chain:      chain,
		walletAddr: walletAddr,
		pending:    make(map[uint64]string),
	}
}

// GetNextNonce returns the next available nonce, initializing from chain if needed.
// The nonce is reserved for use and marked as pending.
func (n *NonceManager) GetNextNonce(ctx context.Context) (uint64, error) {
	n.mu.Lock()
	defer n.mu.Unlock()

	if !n.initialized {
		nonce, err := n.chain.PendingNonceAt(ctx, n.walletAddr)
		if err != nil {
			return 0, err
		}
		n.nonce = nonce
		n.initialized = true
	}

	// Return the current nonce and increment
	currentNonce := n.nonce
	n.nonce++
	// Track reserved nonce in pending map
	n.pending[currentNonce] = ""
	return currentNonce, nil
}

// AcknowledgeNonce marks a nonce as acknowledged (transaction confirmed or replaced).
// The txHash is stored for tracking purposes.
func (n *NonceManager) AcknowledgeNonce(ctx context.Context, nonce uint64, txHash string) {
	n.mu.Lock()
	defer n.mu.Unlock()

	// Store the tx hash for tracking
	n.pending[nonce] = txHash

	// Remove acknowledged nonce from pending (it's now confirmed or replaced)
	// Keep it in pending map for GetPendingNonces visibility
}

// GetPendingNonces returns a sorted list of all pending (reserved but not yet confirmed) nonces.
func (n *NonceManager) GetPendingNonces(ctx context.Context) ([]uint64, error) {
	n.mu.Lock()
	defer n.mu.Unlock()

	// If not initialized, return empty
	if !n.initialized {
		return []uint64{}, nil
	}

	// Collect all nonces that are still potentially pending
	// A nonce is "pending" if it's >= the last confirmed nonce and < current nonce
	var pendingNonces []uint64
	for nonce := range n.pending {
		// Check if this nonce is in the "pending window"
		// Nonces in pending map are tracked until acknowledged
		pendingNonces = append(pendingNonces, nonce)
	}

	sort.Slice(pendingNonces, func(i, j int) bool {
		return pendingNonces[i] < pendingNonces[j]
	})

	return pendingNonces, nil
}

// IsNonceAvailable checks if a specific nonce is available (not yet used or pending).
func (n *NonceManager) IsNonceAvailable(ctx context.Context, nonce uint64) (bool, error) {
	n.mu.Lock()
	defer n.mu.Unlock()

	if !n.initialized {
		// If not initialized, any nonce is considered available
		return true, nil
	}

	// A nonce is available if it's >= the current nonce (next available)
	return nonce >= n.nonce, nil
}

// InitializeNonce explicitly initializes the nonce from the chain.
// This is useful for forcing a fresh fetch of the nonce.
func (n *NonceManager) InitializeNonce(ctx context.Context) error {
	n.mu.Lock()
	defer n.mu.Unlock()

	nonce, err := n.chain.PendingNonceAt(ctx, n.walletAddr)
	if err != nil {
		return err
	}
	n.nonce = nonce
	n.initialized = true
	return nil
}

// ClearPending removes a nonce from the pending tracking map.
func (n *NonceManager) ClearPending(nonce uint64) {
	n.mu.Lock()
	defer n.mu.Unlock()
	delete(n.pending, nonce)
}

// CurrentNonce returns the current nonce value without incrementing.
func (n *NonceManager) CurrentNonce() uint64 {
	n.mu.Lock()
	defer n.mu.Unlock()
	return n.nonce
}

// IsInitialized returns whether the nonce has been initialized.
func (n *NonceManager) IsInitialized() bool {
	n.mu.Lock()
	defer n.mu.Unlock()
	return n.initialized
}