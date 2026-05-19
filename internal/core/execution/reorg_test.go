package execution

import (
	"context"
	"errors"
	"math/big"
	"sync"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockEVMChainForReorg is a mock EVM chain for reorg handler testing.
type mockEVMChainForReorg struct {
	mu       sync.RWMutex
	blocks   map[string]ports.Block // block hash -> block
	info     func() ports.ChainInfo
	getBlock func(ctx context.Context, ref domain.BlockRef) (ports.Block, error)
}

func (m *mockEVMChainForReorg) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	if m.getBlock != nil {
		return m.getBlock(ctx, ref)
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	if block, ok := m.blocks[ref.Hash]; ok {
		return block, nil
	}
	// Return a block with the requested hash if exists in map
	for _, block := range m.blocks {
		if block.Ref.Number == ref.Number {
			return block, nil
		}
	}
	return ports.Block{}, errors.New("block not found")
}

func (m *mockEVMChainForReorg) SetBlock(block ports.Block) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.blocks[block.Ref.Hash] = block
}

func (m *mockEVMChainForReorg) Info() ports.ChainInfo {
	if m.info != nil {
		return m.info()
	}
	return ports.ChainInfo{ID: domain.ChainBase, Name: "Base", NativeSymbol: "ETH", Confirmations: 1}
}

func (m *mockEVMChainForReorg) NonceAt(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error) {
	return 0, nil
}

func (m *mockEVMChainForReorg) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	return 0, nil
}

func (m *mockEVMChainForReorg) SuggestGasFees(ctx context.Context) (baseFee, tip *big.Int, err error) {
	return nil, nil, nil
}

func (m *mockEVMChainForReorg) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	return nil, nil
}

func (m *mockEVMChainForReorg) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}

func (m *mockEVMChainForReorg) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}

func (m *mockEVMChainForReorg) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}

// Ensure mockEVMChainForReorg implements ports.EVMChain for compilation.
var _ ports.EVMChain = (*mockEVMChainForReorg)(nil)

// mockTxRepo is a mock implementation of ports.TxRepo for testing.
type mockTxRepo struct {
	mu           sync.RWMutex
	txs          map[string]domain.SignedTx // hash -> tx
	statuses     map[string]domain.TxStatus
	rbfAttempts  map[string]int
	updateErrors map[string]error // hash -> error to return on UpdateTxStatus
}

func (m *mockTxRepo) GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if tx, ok := m.txs[hash]; ok {
		return tx, nil
	}
	return domain.SignedTx{}, ports.ErrTxNotFound
}

func (m *mockTxRepo) UpdateTxStatus(ctx context.Context, chain domain.ChainID, hash string, newStatus domain.TxStatus, ref *domain.BlockRef) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err, ok := m.updateErrors[hash]; ok && err != nil {
		return err
	}
	m.statuses[hash] = newStatus
	return nil
}

func (m *mockTxRepo) AddTx(tx domain.SignedTx) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.txs[tx.Hash] = tx
	if m.statuses == nil {
		m.statuses = make(map[string]domain.TxStatus)
	}
	m.statuses[tx.Hash] = domain.TxBroadcast
}

func (m *mockTxRepo) SetUpdateError(hash string, err error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.updateErrors == nil {
		m.updateErrors = make(map[string]error)
	}
	m.updateErrors[hash] = err
}

// Ensure mockTxRepo implements ports.TxRepo for compilation.
var _ ports.TxRepo = (*mockTxRepo)(nil)

// Unused TxRepo methods - implement for interface compliance.
func (m *mockTxRepo) UpsertTx(ctx context.Context, tx domain.SignedTx) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.txs[tx.Hash] = tx
	return nil
}

func (m *mockTxRepo) ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error) {
	return nil, nil
}

func (m *mockTxRepo) ListPendingTxs(ctx context.Context, chain domain.ChainID) ([]domain.SignedTx, error) {
	return nil, nil
}

func (m *mockTxRepo) ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error) {
	return nil, nil
}

func (m *mockTxRepo) IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.rbfAttempts[hash]++
	return nil
}

func (m *mockTxRepo) GetRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) (int, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.rbfAttempts[hash], nil
}

// mockBroadcaster is a mock implementation of ports.Broadcaster for testing.
type mockBroadcaster struct {
	mu         sync.RWMutex
	sendCalls  []domain.SignedTx
	sendError  error
	callCount  int64
}

func (m *mockBroadcaster) Send(ctx context.Context, tx domain.SignedTx) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sendCalls = append(m.sendCalls, tx)
	m.callCount++
	if m.sendError != nil {
		return m.sendError
	}
	// Simulate successful broadcast by setting hash if empty
	return nil
}

func (m *mockBroadcaster) CallCount() int64 {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.callCount
}

func (m *mockBroadcaster) GetLastSent() (domain.SignedTx, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if len(m.sendCalls) == 0 {
		return domain.SignedTx{}, false
	}
	return m.sendCalls[len(m.sendCalls)-1], true
}

// Ensure mockBroadcaster implements ports.Broadcaster for compilation.
var _ ports.Broadcaster = (*mockBroadcaster)(nil)

// mockBus is a mock implementation of ports.Bus for testing.
type mockBus struct {
	mu       sync.RWMutex
	events   []domain.Event
	publishError error
}

func (m *mockBus) Publish(event domain.Event) error {
	if m.publishError != nil {
		return m.publishError
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, event)
	return nil
}

func (m *mockBus) Subscribe(topic string, handler ports.EventHandler) (ports.Subscription, error) {
	return nil, nil
}

func (m *mockBus) GetEvents() []domain.Event {
	m.mu.RLock()
	defer m.mu.RUnlock()
	events := make([]domain.Event, len(m.events))
	copy(events, m.events)
	return events
}

// Ensure mockBus implements ports.Bus for compilation.
var _ ports.Bus = (*mockBus)(nil)

// mockNonceManager is a mock NonceManager for testing.
type mockNonceManager struct {
	mu          sync.Mutex
	nonces      []uint64 // queue of nonces to return
	pending     map[uint64]bool
	current     uint64
	getNextErr  error
}

func (m *mockNonceManager) GetNextNonce(ctx context.Context) (uint64, error) {
	if m.getNextErr != nil {
		return 0, m.getNextErr
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.nonces) > 0 {
		nonce := m.nonces[0]
		m.nonces = m.nonces[1:]
		if m.pending == nil {
			m.pending = make(map[uint64]bool)
		}
		m.pending[nonce] = true
		return nonce, nil
	}
	m.current++
	if m.pending == nil {
		m.pending = make(map[uint64]bool)
	}
	m.pending[m.current] = true
	return m.current, nil
}

func (m *mockNonceManager) SetNextNonces(nonces ...uint64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.nonces = nonces
}

func (m *mockNonceManager) ClearPending(nonce uint64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.pending != nil {
		delete(m.pending, nonce)
	}
}

func (m *mockNonceManager) GetPendingNonces() []uint64 {
	m.mu.Lock()
	defer m.mu.Unlock()
	var result []uint64
	for nonce := range m.pending {
		result = append(result, nonce)
	}
	return result
}

// Helper function to convert int to *big.Int
func intToBigInt(i int) *big.Int {
	return big.NewInt(int64(i))
}

// TestReorgHandler_DetectReorg tests the DetectReorg method.
func TestReorgHandler_DetectReorg(t *testing.T) {
	t.Run("detects reorg when block hash changes", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			blocks: make(map[string]ports.Block),
		}

		txRepo := &mockTxRepo{txs: make(map[string]domain.SignedTx)}
		broadcaster := &mockBroadcaster{}
		bus := &mockBus{}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      txRepo,
			Broadcaster: broadcaster,
			Bus:         bus,
			NonceMgr:    nil, // not needed for detect test
		})

		txHash := "0xtxhash123"
		originalBlock := domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 100,
			Hash:   "0xoriginalhash",
		}

		// Track transaction with original block
		handler.TrackTransaction(txHash, originalBlock, 5, []byte("raw tx data"))

		// Set original block
		chain.SetBlock(ports.Block{
			Ref: originalBlock,
		})

		// First detection should find the block (no reorg)
		reorged, err := handler.DetectReorg(context.Background(), txHash)
		require.NoError(t, err)
		assert.False(t, reorged, "should not detect reorg when block hash matches")

		// Simulate reorg: change the block hash in the chain
		chain.getBlock = func(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
			// Return block with different hash to simulate reorg
			return ports.Block{
				Ref: domain.BlockRef{
					Chain:  domain.ChainBase,
					Number: 100,
					Hash:   "0xreorgedhash", // Different hash
				},
			}, nil
		}

		// Detection should now find reorg
		reorged, err = handler.DetectReorg(context.Background(), txHash)
		require.NoError(t, err)
		assert.True(t, reorged, "should detect reorg when block hash changed")
	})

	t.Run("returns error for untracked tx", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			blocks: make(map[string]ports.Block),
		}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil,
		})

		reorged, err := handler.DetectReorg(context.Background(), "0xuntracked")
		assert.Error(t, err)
		assert.Equal(t, ErrTxNotTracked, err)
		assert.False(t, reorged)
	})
}

// TestReorgHandler_HandleReorg tests the HandleReorg method.
func TestReorgHandler_HandleReorg(t *testing.T) {
	t.Run("successfully handles reorg and rebroadcasts", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			blocks: make(map[string]ports.Block),
			info: func() ports.ChainInfo {
				return ports.ChainInfo{ID: domain.ChainBase}
			},
		}
		txRepo := &mockTxRepo{txs: make(map[string]domain.SignedTx)}
		broadcaster := &mockBroadcaster{}
		bus := &mockBus{}

		// Use a wrapper to adapt mockNonceManager to *NonceManager
		mockNm := &mockNonceManagerForHandler{}
		nonceMgr := &NonceManagerWrapper{
			mock: mockNm,
		}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      txRepo,
			Broadcaster: broadcaster,
			Bus:         bus,
			NonceMgr:    nonceMgr,
		})

		txHash := "0xoriginaltx"
		originalBlock := domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 100,
			Hash:   "0xoriginalhash",
		}

		// Add original transaction to repo
		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
				From:  domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
				To:    domain.MustParseAddress("0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"),
				Data:  []byte("original tx data"),
				Nonce: 5,
			},
			Signature: []byte("signature"),
			Hash:      txHash,
		}
		txRepo.AddTx(tx)

		// Track transaction
		handler.TrackTransaction(txHash, originalBlock, 5, []byte("original tx data"))

		// Handle reorg
		err := handler.HandleReorg(context.Background(), txHash)
		require.NoError(t, err)

		// Verify tx status was updated to reorged
		status, _ := txRepo.statuses[txHash]
		assert.Equal(t, domain.TxReorged, status)

		// Verify new tx was broadcast
		assert.Equal(t, int64(1), broadcaster.CallCount())

		// Verify reorg event was recorded
		events := bus.GetEvents()
		assert.Len(t, events, 1)
		assert.Equal(t, "live.reorg.detected", events[0].Topic)
	})

	t.Run("returns error for untracked tx", func(t *testing.T) {
		handler := NewReorgHandler(ReorgDependencies{
			Chain:       &mockEVMChainForReorg{},
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil, // not needed for untracked tx check
		})

		err := handler.HandleReorg(context.Background(), "0xuntracked")
		assert.Error(t, err)
		assert.Equal(t, ErrTxNotTracked, err)
	})

	t.Run("returns error when max retries exceeded", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			info: func() ports.ChainInfo { return ports.ChainInfo{ID: domain.ChainBase} },
		}
		txRepo := &mockTxRepo{txs: make(map[string]domain.SignedTx)}
		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      txRepo,
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil, // not needed for max retries check
		})

		txHash := "0xtxwithmaxretries"

		// Track with max retries
		handler.TrackTransaction(txHash, domain.BlockRef{Chain: domain.ChainBase, Number: 1, Hash: "0xhash"}, 5, []byte("data"))
		state, _ := handler.GetReorgState(txHash)
		state.Attempts = MaxReorgRetries // Set to max

		err := handler.HandleReorg(context.Background(), txHash)
		assert.Error(t, err)
		assert.Equal(t, ErrReorgMaxRetries, err)
	})

	t.Run("clears nonce and gets new one on reorg", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			info: func() ports.ChainInfo { return ports.ChainInfo{ID: domain.ChainBase} },
		}
		txRepo := &mockTxRepo{txs: make(map[string]domain.SignedTx)}
		broadcaster := &mockBroadcaster{}
		bus := &mockBus{}

		mockNm := &mockNonceManagerForHandler{clearCalls: make([]uint64, 0)}
		nonceMgr := &NonceManagerWrapper{mock: mockNm}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      txRepo,
			Broadcaster: broadcaster,
			Bus:         bus,
			NonceMgr:    nonceMgr,
		})

		txHash := "0xtxnonceclear"
		tx := domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
				From:  domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
				To:    domain.MustParseAddress("0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"),
				Data:  []byte("tx data"),
				Nonce: 5,
			},
			Signature: []byte("sig"),
			Hash:      txHash,
		}
		txRepo.AddTx(tx)

		handler.TrackTransaction(txHash, domain.BlockRef{Chain: domain.ChainBase, Number: 1, Hash: "0xhash"}, 5, []byte("tx data"))

		err := handler.HandleReorg(context.Background(), txHash)
		require.NoError(t, err)

		// Verify old nonce was cleared
		assert.Contains(t, mockNm.clearCalls, uint64(5), "old nonce should be cleared")

		// Verify new nonce was requested
		assert.Equal(t, 1, mockNm.getNextCalls, "GetNextNonce should be called once")
	})
}

// TestReorgHandler_MonitorBlock tests the MonitorBlock method.
func TestReorgHandler_MonitorBlock(t *testing.T) {
	t.Run("detects reorg via block hash change", func(t *testing.T) {
		blockHash := "0xblockhash"
		block := domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 100,
			Hash:   blockHash,
		}

		// Create chain with getBlock function that returns the block
		chain := &mockEVMChainForReorg{
			blocks: make(map[string]ports.Block),
			getBlock: func(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
				// Initially return the original block
				return ports.Block{Ref: block}, nil
			},
		}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil,
		})

		// Track a transaction in this block
		handler.TrackTransaction("0xtx1", block, 5, []byte("data"))

		// Monitor block when hash matches
		reorged, err := handler.MonitorBlock(context.Background(), blockHash)
		require.NoError(t, err)
		assert.False(t, reorged, "no reorg when hash matches")

		// Simulate reorg: change the block hash
		chain.getBlock = func(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
			return ports.Block{
				Ref: domain.BlockRef{
					Chain:  domain.ChainBase,
					Number: 100,
					Hash:   "0xdifferenthash", // Reorged hash
				},
			}, nil
		}

		reorged, err = handler.MonitorBlock(context.Background(), blockHash)
		require.NoError(t, err)
		assert.True(t, reorged, "reorg detected when hash changed")
	})

	t.Run("returns false for untracked block", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			blocks: make(map[string]ports.Block),
		}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil,
		})

		// Monitor a block with no tracked transactions
		reorged, err := handler.MonitorBlock(context.Background(), "0xuntrackedblock")
		require.NoError(t, err)
		assert.False(t, reorged, "no reorg for untracked block")
	})
}

// TestReorgHandler_RecordReorgEvent tests the RecordReorgEvent method.
func TestReorgHandler_RecordReorgEvent(t *testing.T) {
	t.Run("records reorg event on bus", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			info: func() ports.ChainInfo { return ports.ChainInfo{ID: domain.ChainBase} },
		}
		bus := &mockBus{}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         bus,
			NonceMgr:    nil,
		})

		err := handler.RecordReorgEvent(context.Background(), "0xtxhash", "test reorg reason")
		require.NoError(t, err)

		events := bus.GetEvents()
		require.Len(t, events, 1)

		event := events[0]
		assert.Equal(t, "live.reorg.detected", event.Topic)
		assert.Equal(t, domain.EnvLive, event.Env)

		// Parse payload
		var payload ReorgAuditPayload
		err = event.PayloadAs(&payload)
		require.NoError(t, err)
		assert.Equal(t, "0xtxhash", payload.TxHash)
		assert.Equal(t, "test reorg reason", payload.Reason)
		assert.Equal(t, domain.ChainBase, payload.Chain)
		assert.Greater(t, payload.Timestamp, int64(0))
	})

	t.Run("returns error when bus publish fails", func(t *testing.T) {
		chain := &mockEVMChainForReorg{
			info: func() ports.ChainInfo { return ports.ChainInfo{ID: domain.ChainBase} },
		}
		bus := &mockBus{publishError: errors.New("bus unavailable")}

		handler := NewReorgHandler(ReorgDependencies{
			Chain:       chain,
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         bus,
			NonceMgr:    nil,
		})

		err := handler.RecordReorgEvent(context.Background(), "0xtxhash", "reason")
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "bus unavailable")
	})
}

// TestReorgHandler_TrackTransaction tests transaction tracking.
func TestReorgHandler_TrackTransaction(t *testing.T) {
	t.Run("tracks and retrieves transaction state", func(t *testing.T) {
		handler := NewReorgHandler(ReorgDependencies{
			Chain:       &mockEVMChainForReorg{},
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil,
		})

		txHash := "0xtxhash"
		block := domain.BlockRef{
			Chain:  domain.ChainBase,
			Number: 100,
			Hash:   "0xblockhash",
		}
		nonce := uint64(5)
		rawTx := []byte("raw tx data")

		handler.TrackTransaction(txHash, block, nonce, rawTx)

		state, exists := handler.GetReorgState(txHash)
		require.True(t, exists)
		assert.Equal(t, block, state.OriginalBlock)
		assert.Equal(t, nonce, state.Nonce)
		assert.Equal(t, rawTx, state.RawTx)
		assert.Equal(t, 0, state.Attempts)
	})

	t.Run("untrack removes transaction", func(t *testing.T) {
		handler := NewReorgHandler(ReorgDependencies{
			Chain:       &mockEVMChainForReorg{},
			TxRepo:      &mockTxRepo{},
			Broadcaster: &mockBroadcaster{},
			Bus:         &mockBus{},
			NonceMgr:    nil,
		})

		txHash := "0xtxhash"
		handler.TrackTransaction(txHash, domain.BlockRef{Chain: domain.ChainBase, Number: 1, Hash: "0xhash"}, 5, []byte("data"))

		// Verify exists
		_, exists := handler.GetReorgState(txHash)
		assert.True(t, exists)

		// Untrack
		handler.UntrackTransaction(txHash)

		// Verify gone
		_, exists = handler.GetReorgState(txHash)
		assert.False(t, exists)
	})
}

// NonceManagerWrapper wraps mockNonceManagerForHandler to implement NonceManagerForReorg.
type NonceManagerWrapper struct {
	mock *mockNonceManagerForHandler
}

func (n *NonceManagerWrapper) GetNextNonce(ctx context.Context) (uint64, error) {
	n.mock.mu.Lock()
	defer n.mock.mu.Unlock()
	n.mock.getNextCalls++
	if n.mock.getNextErr != nil {
		return 0, n.mock.getNextErr
	}
	if len(n.mock.nonces) > 0 {
		nonce := n.mock.nonces[0]
		n.mock.nonces = n.mock.nonces[1:]
		return nonce, nil
	}
	n.mock.current++
	return n.mock.current, nil
}

func (n *NonceManagerWrapper) ClearPending(nonce uint64) {
	n.mock.ClearPending(nonce)
}

// mockNonceManagerForHandler is a mock for testing with the reorg handler.
type mockNonceManagerForHandler struct {
	mu           sync.Mutex
	nonces       []uint64
	pending      map[uint64]bool
	current      uint64
	getNextErr   error
	getNextCalls int
	clearCalls   []uint64
}

func (m *mockNonceManagerForHandler) SetNextNonces(nonces ...uint64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.nonces = nonces
}

func (m *mockNonceManagerForHandler) GetPendingNonces() []uint64 {
	m.mu.Lock()
	defer m.mu.Unlock()
	var result []uint64
	for nonce := range m.pending {
		result = append(result, nonce)
	}
	return result
}

func (m *mockNonceManagerForHandler) ClearPending(nonce uint64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.clearCalls = append(m.clearCalls, nonce)
	if m.pending != nil {
		delete(m.pending, nonce)
	}
}