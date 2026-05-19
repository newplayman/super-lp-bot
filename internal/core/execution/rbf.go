package execution

import (
	"context"
	"errors"
	"math/big"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// ErrMaxRBFAttemptsExceeded is returned when RBF attempts exceed the maximum.
var ErrMaxRBFAttemptsExceeded = errors.New("max RBF attempts exceeded")

// ErrTransactionNotFound is returned when a transaction is not tracked.
var ErrTransactionNotFound = errors.New("transaction not found")

// ErrCannotRBF is returned when RBF is not allowed for a transaction.
var ErrCannotRBF = errors.New("RBF not allowed for this transaction")

// RBFConfig holds configuration for the RBF manager.
type RBFConfig struct {
	// MaxAttempts is the maximum number of RBF attempts per transaction.
	MaxAttempts int
	// GasIncreasePct is the percentage increase for gas price (e.g., 25.0 for 25%).
	GasIncreasePct float64
	// StuckTimeout is the duration after which a transaction is considered stuck.
	StuckTimeout time.Duration
}

// DefaultRBFConfig returns the default RBF configuration.
func DefaultRBFConfig() RBFConfig {
	return RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   5 * time.Minute,
	}
}

// rbfTxState tracks the state of a transaction for RBF.
type rbfTxState struct {
	originalHash string
	nonce       uint64
	attempts    int
	lastAttempt time.Time
}

// NonceManagerInterface defines the interface for nonce management.
// This allows RBF to work with different nonce manager implementations.
type NonceManagerInterface interface {
	GetNextNonce(ctx context.Context) (uint64, error)
	AcknowledgeNonce(ctx context.Context, nonce uint64, txHash string)
	GetPendingNonces(ctx context.Context) ([]uint64, error)
	IsNonceAvailable(ctx context.Context, nonce uint64) (bool, error)
	InitializeNonce(ctx context.Context) error
	ClearPending(nonce uint64)
	CurrentNonce() uint64
	IsInitialized() bool
}

// RBFManager handles Replace-By-Fee for stuck transactions.
type RBFManager struct {
	config   RBFConfig
	chain    ports.EVMChain
	nonceMgr NonceManagerInterface
	txs      map[string]*rbfTxState
	mu       sync.RWMutex
}

// NewRBFManager creates a new RBFManager with the given configuration.
func NewRBFManager(config RBFConfig, chain ports.EVMChain, nonceMgr NonceManagerInterface) *RBFManager {
	if config.MaxAttempts == 0 {
		config.MaxAttempts = 3
	}
	if config.GasIncreasePct == 0 {
		config.GasIncreasePct = 25.0
	}
	if config.StuckTimeout == 0 {
		config.StuckTimeout = 5 * time.Minute
	}

	return &RBFManager{
		config:   config,
		chain:    chain,
		nonceMgr: nonceMgr,
		txs:      make(map[string]*rbfTxState),
	}
}

// IsStuck checks if a transaction is considered stuck based on timeout.
func (r *RBFManager) IsStuck(ctx context.Context, txHash string) (bool, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	state, exists := r.txs[txHash]
	if !exists {
		// Not tracked, not stuck
		return false, nil
	}

	// Check if enough time has passed since last attempt
	return time.Since(state.lastAttempt) >= r.config.StuckTimeout, nil
}

// CanRBF checks if RBF is allowed for a transaction.
func (r *RBFManager) CanRBF(ctx context.Context, txHash string) (bool, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	state, exists := r.txs[txHash]
	if !exists {
		// Not tracked, can try
		return true, nil
	}

	// Check max attempts
	return state.attempts < r.config.MaxAttempts, nil
}

// GetRBFAttempts returns the number of RBF attempts for a transaction.
func (r *RBFManager) GetRBFAttempts(txHash string) int {
	r.mu.RLock()
	defer r.mu.RUnlock()

	state, exists := r.txs[txHash]
	if !exists {
		return 0
	}
	return state.attempts
}

// RecordAttempt records an RBF attempt for a transaction.
// The nonce will be obtained from the nonce manager if not already tracked.
func (r *RBFManager) RecordAttempt(txHash string) {
	r.mu.Lock()
	defer r.mu.Unlock()

	state, exists := r.txs[txHash]
	if !exists {
		state = &rbfTxState{
			originalHash: txHash,
		}
		r.txs[txHash] = state
	}

	state.attempts++
	state.lastAttempt = time.Now()
}

// ClearAttempts clears the RBF attempts for a transaction (e.g., after successful replacement).
func (r *RBFManager) ClearAttempts(txHash string) {
	r.mu.Lock()
	defer r.mu.Unlock()

	delete(r.txs, txHash)
}

// AttemptRBF creates a replacement transaction with higher gas price.
// The original transaction hash is used to track the RBF attempts.
func (r *RBFManager) AttemptRBF(ctx context.Context, txHash string) (*ReplacementTx, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Check if we can RBF
	state, exists := r.txs[txHash]
	if exists && state.attempts >= r.config.MaxAttempts {
		return nil, ErrMaxRBFAttemptsExceeded
	}

	// Get current gas fees
	baseFee, tip, err := r.chain.SuggestGasFees(ctx)
	if err != nil {
		return nil, err
	}

	// Increase gas price by the configured percentage
	increaseFactor := 1 + (r.config.GasIncreasePct / 100.0)
	newTip := new(big.Int).Mul(tip, big.NewInt(int64(increaseFactor*100)))
	newTip.Div(newTip, big.NewInt(100))

	newBaseFee := new(big.Int).Mul(baseFee, big.NewInt(int64(increaseFactor*100)))
	newBaseFee.Div(newBaseFee, big.NewInt(100))

	// Get nonce from state or request new
	var nonce uint64
	if exists {
		nonce = state.nonce
	} else {
		nonce, err = r.nonceMgr.GetNextNonce(ctx)
		if err != nil {
			return nil, err
		}
	}

	// Create replacement transaction with same nonce
	replacement := &ReplacementTx{
		Chain:    domain.ChainBase,
		Nonce:    nonce,
		BaseFee:  newBaseFee,
		Priority: newTip,
	}

	// Update state
	if !exists {
		state = &rbfTxState{
			originalHash: txHash,
			nonce:       nonce,
		}
		r.txs[txHash] = state
	}
	state.attempts++
	state.lastAttempt = time.Now()

	return replacement, nil
}

// ReplacementTx represents a replacement transaction for RBF.
// This is a simplified representation that wraps UnsignedTx with RBF-specific data.
type ReplacementTx struct {
	Chain    domain.ChainID
	Nonce    uint64
	BaseFee  *big.Int
	Priority *big.Int
}

// ToUnsignedTx converts the replacement transaction to an UnsignedTx.
func (r *ReplacementTx) ToUnsignedTx() domain.UnsignedTx {
	return domain.UnsignedTx{
		Chain: r.Chain,
		Nonce: r.Nonce,
	}
}

// AttemptRBFWithOriginal creates a replacement transaction using the original transaction as base.
// This version takes the original transaction and creates a replacement with higher gas.
func (r *RBFManager) AttemptRBFWithOriginal(ctx context.Context, originalHash string, originalTx domain.UnsignedTx) (*ReplacementTx, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Check if we can RBF
	state, exists := r.txs[originalHash]
	if exists && state.attempts >= r.config.MaxAttempts {
		return nil, ErrMaxRBFAttemptsExceeded
	}

	// Get current gas fees
	baseFee, tip, err := r.chain.SuggestGasFees(ctx)
	if err != nil {
		return nil, err
	}

	// Increase gas price by the configured percentage
	increaseFactor := 1 + (r.config.GasIncreasePct / 100.0)
	newTip := new(big.Int).Mul(tip, big.NewInt(int64(increaseFactor*100)))
	newTip.Div(newTip, big.NewInt(100))

	newBaseFee := new(big.Int).Mul(baseFee, big.NewInt(int64(increaseFactor*100)))
	newBaseFee.Div(newBaseFee, big.NewInt(100))

	// Create replacement transaction with same nonce as original
	replacement := &ReplacementTx{
		Chain:    originalTx.Chain,
		Nonce:    originalTx.Nonce,
		BaseFee:  newBaseFee,
		Priority: newTip,
	}

	// Update state
	if !exists {
		state = &rbfTxState{
			originalHash: originalHash,
			nonce:       originalTx.Nonce,
		}
		r.txs[originalHash] = state
	}
	state.attempts++
	state.lastAttempt = time.Now()
	state.nonce = originalTx.Nonce

	return replacement, nil
}

// GetState returns the current state of an RBF-tracked transaction.
func (r *RBFManager) GetState(txHash string) (attempts int, lastAttempt time.Time, exists bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	state, found := r.txs[txHash]
	if !found {
		return 0, time.Time{}, false
	}
	return state.attempts, state.lastAttempt, true
}