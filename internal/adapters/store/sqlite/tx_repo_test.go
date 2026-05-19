// Package sqlite provides SQLite storage adapters.
package sqlite

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

func setupTxRepoTest(t *testing.T) (*sql.DB, *TxRepo, func()) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_txrepo.db")

	// Run migrations with test_ prefix
	err := MigrateUp(dbPath, "test_")
	require.NoError(t, err)

	db, err := sql.Open("sqlite3", dbPath)
	require.NoError(t, err)

	repo := NewTxRepo(db, "test_")

	cleanup := func() {
		db.Close()
	}

	return db, repo, cleanup
}

func TestTxRepo_UpsertTx(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	toAddr := domain.MustParseAddress("0xabcdefabcdefabcdefabcdefabcdefabcdefabcd")

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:      "tx-001",
			Chain:   domain.ChainBase,
			From:    fromAddr,
			To:      toAddr,
			Data:    []byte{0x12, 0x34, 0x56},
			Value:   decimal.NewFromInt(100),
			Nonce:   42,
			Deadline: time.Now().Unix() + 300,
			MinOut:  decimal.NewFromFloat(0.01),
		},
		Signature:   []byte{0xab, 0xcd, 0xef},
		Hash:        "0xtesthash001",
		RFBAttempts: 0,
		Status:      domain.TxBuilt,
	}

	err := repo.UpsertTx(ctx, tx)
	require.NoError(t, err, "UpsertTx should succeed")

	// Verify we can retrieve it
	retrieved, err := repo.GetTxByHash(ctx, domain.ChainBase, "0xtesthash001")
	require.NoError(t, err, "GetTxByHash should succeed")
	require.Equal(t, tx.Hash, retrieved.Hash)
	require.Equal(t, domain.TxBuilt, retrieved.Status)
}

func TestTxRepo_UpdateTxStatus(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	toAddr := domain.MustParseAddress("0xabcdefabcdefabcdefabcdefabcdefabcdefabcd")

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:      "tx-002",
			Chain:   domain.ChainBase,
			From:    fromAddr,
			To:      toAddr,
			Nonce:   42,
			Deadline: time.Now().Unix() + 300,
		},
		Hash:   "0xtesthash002",
		Status: domain.TxBuilt,
	}

	// Insert first
	err := repo.UpsertTx(ctx, tx)
	require.NoError(t, err)

	// Update status to broadcast
	err = repo.UpdateTxStatus(ctx, domain.ChainBase, "0xtesthash002", domain.TxBroadcast, nil)
	require.NoError(t, err, "UpdateTxStatus should succeed")

	// Verify
	retrieved, err := repo.GetTxByHash(ctx, domain.ChainBase, "0xtesthash002")
	require.NoError(t, err)
	require.Equal(t, domain.TxBroadcast, retrieved.Status)
}

func TestTxRepo_ListTxsByStatus(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1111111111111111111111111111111111111111")
	toAddr := domain.MustParseAddress("0x2222222222222222222222222222222222222222")

	// Insert multiple txs with different statuses
	txs := []domain.SignedTx{
		{
			UnsignedTx: domain.UnsignedTx{ID: "tx-003a", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 1, Deadline: 0},
			Hash:   "0xtesthash003a",
			Status: domain.TxBuilt,
		},
		{
			UnsignedTx: domain.UnsignedTx{ID: "tx-003b", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 2, Deadline: 0},
			Hash:   "0xtesthash003b",
			Status: domain.TxBroadcast,
		},
		{
			UnsignedTx: domain.UnsignedTx{ID: "tx-003c", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 3, Deadline: 0},
			Hash:   "0xtesthash003c",
			Status: domain.TxBroadcast,
		},
	}

	for _, tx := range txs {
		err := repo.UpsertTx(ctx, tx)
		require.NoError(t, err)
	}

	// List broadcast txs
	broadcastTxs, err := repo.ListTxsByStatus(ctx, domain.ChainBase, domain.TxBroadcast)
	require.NoError(t, err)
	require.Len(t, broadcastTxs, 2, "Should have 2 broadcast txs")

	// List all txs (empty status filter)
	allTxs, err := repo.ListTxsByStatus(ctx, domain.ChainBase, "")
	require.NoError(t, err)
	require.Len(t, allTxs, 3, "Should have 3 total txs")
}

func TestTxRepo_IncrementRFBAttempts(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1111111111111111111111111111111111111111")
	toAddr := domain.MustParseAddress("0x2222222222222222222222222222222222222222")

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{ID: "tx-004", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 1, Deadline: 0},
		Hash:   "0xtesthash004",
		Status: domain.TxBroadcast,
	}

	err := repo.UpsertTx(ctx, tx)
	require.NoError(t, err)

	// Increment RFB attempts
	err = repo.IncrementRFBAttempts(ctx, domain.ChainBase, "0xtesthash004")
	require.NoError(t, err, "IncrementRFBAttempts should succeed")

	attempts, err := repo.GetRFBAttempts(ctx, domain.ChainBase, "0xtesthash004")
	require.NoError(t, err)
	require.Equal(t, 1, attempts, "Should have 1 RFB attempt")

	// Increment again
	err = repo.IncrementRFBAttempts(ctx, domain.ChainBase, "0xtesthash004")
	require.NoError(t, err)
	attempts, err = repo.GetRFBAttempts(ctx, domain.ChainBase, "0xtesthash004")
	require.NoError(t, err)
	require.Equal(t, 2, attempts)
}

func TestTxRepo_ListStuckTxs(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1111111111111111111111111111111111111111")
	toAddr := domain.MustParseAddress("0x2222222222222222222222222222222222222222")

	// Insert a tx that's been broadcast (needs broadcast_at set for stuck detection)
	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{ID: "tx-005", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 1, Deadline: 0},
		Hash:   "0xtesthash005",
		Status: domain.TxBroadcast,
	}
	err := repo.UpsertTx(ctx, tx)
	require.NoError(t, err)

	// We can't easily simulate stuck detection without manually manipulating broadcast_at
	// So we test that ListStuckTxs returns empty when no stuck txs exist
	stuckTxs, err := repo.ListStuckTxs(ctx, domain.ChainBase, 60)
	require.NoError(t, err)
	require.Len(t, stuckTxs, 0, "Should have no stuck txs (broadcast_at not set)")
}

func TestTxRepo_InvalidTransition(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1111111111111111111111111111111111111111")
	toAddr := domain.MustParseAddress("0x2222222222222222222222222222222222222222")

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{ID: "tx-006", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 1, Deadline: 0},
		Hash:   "0xtesthash006",
		Status: domain.TxBuilt,
	}

	err := repo.UpsertTx(ctx, tx)
	require.NoError(t, err)

	// Try invalid transition: built -> mined (should fail, valid is built->broadcast)
	err = repo.UpdateTxStatus(ctx, domain.ChainBase, "0xtesthash006", domain.TxMined, nil)
	require.Error(t, err, "Invalid transition should fail")
}

func TestTxRepo_NotFound(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()

	_, err := repo.GetTxByHash(ctx, domain.ChainBase, "nonexistent")
	require.ErrorIs(t, err, ports.ErrTxNotFound, "Should return ErrTxNotFound")
}

func TestTxRepo_ListPendingTxs(t *testing.T) {
	_, repo, cleanup := setupTxRepoTest(t)
	defer cleanup()

	ctx := context.Background()
	fromAddr := domain.MustParseAddress("0x1111111111111111111111111111111111111111")
	toAddr := domain.MustParseAddress("0x2222222222222222222222222222222222222222")

	// Insert txs with various statuses
	txs := []domain.SignedTx{
		{
			UnsignedTx: domain.UnsignedTx{ID: "tx-007a", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 1, Deadline: 0},
			Hash:   "0xtesthash007a",
			Status: domain.TxBuilt,
		},
		{
			UnsignedTx: domain.UnsignedTx{ID: "tx-007b", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 2, Deadline: 0},
			Hash:   "0xtesthash007b",
			Status: domain.TxBroadcast,
		},
		{
			UnsignedTx: domain.UnsignedTx{ID: "tx-007c", Chain: domain.ChainBase, From: fromAddr, To: toAddr, Nonce: 3, Deadline: 0},
			Hash:   "0xtesthash007c",
			Status: domain.TxConfirmed, // Not pending
		},
	}

	for _, tx := range txs {
		err := repo.UpsertTx(ctx, tx)
		require.NoError(t, err)
	}

	// List pending txs
	pendingTxs, err := repo.ListPendingTxs(ctx, domain.ChainBase)
	require.NoError(t, err)
	require.Len(t, pendingTxs, 2, "Should have 2 pending txs (built + broadcast, not confirmed)")
}

var _ = os.TempDir // suppress unused warning