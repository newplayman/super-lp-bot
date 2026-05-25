//go:build live

package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"math/big"
	"path/filepath"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/stretchr/testify/require"
)

type fakeBaseReceiptSource struct {
	receipts map[string]*types.Receipt
}

func (f *fakeBaseReceiptSource) TransactionReceipt(_ context.Context, hash common.Hash) (*types.Receipt, error) {
	if receipt, ok := f.receipts[hash.Hex()]; ok {
		return receipt, nil
	}
	return nil, ethereum.NotFound
}

func TestReconcileBasePendingTxs_MintReceiptConfirmsAndOpensPosition(t *testing.T) {
	store := newLiveReconcileTestStore(t)
	ctx := context.Background()
	cfg := liveReconcileTestConfig()
	txHash := "0x1111111111111111111111111111111111111111111111111111111111111111"
	wallet := "0x2222222222222222222222222222222222222222"
	npm := common.HexToAddress(cfg.Execution.NPMBaseAddress)

	position := &domain.Position{
		ID:           "pos-open-1",
		PoolID:       "0x3333333333333333333333333333333333333333",
		Chain:        domain.ChainBase,
		Status:       domain.StatusOpening,
		Tier:         domain.TierC,
		AmountUSD:    domain.MustDecimal("10"),
		OpenTxHash:   txHash,
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, position))
	intent := newExecutionIntent("live_open", domain.ChainBase, position.PoolID, position.ID, "open", "test", time.Now())
	intent.TxHash = txHash
	intent.SignedTxHash = txHash
	require.NoError(t, store.ExecutionIntentRepo().Reserve(ctx, intent))
	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "mint-open-1",
			Chain:    domain.ChainBase,
			From:     domain.MustParseAddress(wallet),
			To:       domain.MustParseAddress(cfg.Execution.NPMBaseAddress),
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxSubmittedPrivate,
	}))

	receipt := mintReceiptFixture(t, common.HexToHash(txHash), npm, wallet, "123", "1000", "2500000", "500000000000000")
	source := &fakeBaseReceiptSource{receipts: map[string]*types.Receipt{common.HexToHash(txHash).Hex(): receipt}}

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, source, nil, time.Now()))

	tx, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.TxConfirmed, tx.Status)

	updated, err := store.PositionRepo().FindByID(ctx, position.ID)
	require.NoError(t, err)
	require.Equal(t, domain.StatusOpen, updated.Status)
	require.Equal(t, "123", updated.TokenID)
	require.Equal(t, txHash, updated.OpenTxHash)

	var metadata map[string]any
	require.NoError(t, json.Unmarshal([]byte(updated.MetadataJSON), &metadata))
	require.Equal(t, "1000", metadata["liquidity"])
	require.Equal(t, "2500000", metadata["actual_amount0"])
	require.Equal(t, "500000000000000", metadata["actual_amount1"])
	storedIntent, err := store.ExecutionIntentRepo().FindByTxHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.IntentStatusReconciled, storedIntent.Status)

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, source, nil, time.Now()))
	rechecked, err := store.PositionRepo().FindByID(ctx, position.ID)
	require.NoError(t, err)
	require.Equal(t, domain.StatusOpen, rechecked.Status)
	require.Equal(t, "123", rechecked.TokenID)
}

func TestReconcileBasePendingTxs_RevertedMintRejectsOpeningPosition(t *testing.T) {
	store := newLiveReconcileTestStore(t)
	ctx := context.Background()
	cfg := liveReconcileTestConfig()
	txHash := "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

	position := &domain.Position{
		ID:           "pos-open-revert",
		PoolID:       "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		Chain:        domain.ChainBase,
		Status:       domain.StatusOpening,
		Tier:         domain.TierC,
		AmountUSD:    domain.MustDecimal("10"),
		OpenTxHash:   txHash,
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, position))
	intent := newExecutionIntent("live_open", domain.ChainBase, position.PoolID, position.ID, "open", "test", time.Now())
	intent.TxHash = txHash
	intent.SignedTxHash = txHash
	require.NoError(t, store.ExecutionIntentRepo().Reserve(ctx, intent))
	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "mint-open-revert",
			Chain:    domain.ChainBase,
			From:     zeroEVMAddress(),
			To:       domain.MustParseAddress(cfg.Execution.NPMBaseAddress),
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxSubmittedPrivate,
	}))

	source := &fakeBaseReceiptSource{receipts: map[string]*types.Receipt{
		common.HexToHash(txHash).Hex(): {
			TxHash:      common.HexToHash(txHash),
			Status:      types.ReceiptStatusFailed,
			BlockNumber: newTestBigInt(101),
			BlockHash:   common.HexToHash("0x1"),
		},
	}}

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, source, nil, time.Now()))

	tx, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.TxReverted, tx.Status)

	updated, err := store.PositionRepo().FindByID(ctx, position.ID)
	require.NoError(t, err)
	require.Equal(t, domain.StatusRejected, updated.Status)
	storedIntent, err := store.ExecutionIntentRepo().FindByTxHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.IntentStatusFailed, storedIntent.Status)
}

func TestReconcileBasePendingTxs_StuckRevertedOpeningPositionBecomesRejected(t *testing.T) {
	store := newLiveReconcileTestStore(t)
	ctx := context.Background()
	cfg := liveReconcileTestConfig()
	txHash := "0xabababababababababababababababababababababababababababababababab"

	position := &domain.Position{
		ID:           "pos-open-stuck-revert",
		PoolID:       "0xcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
		Chain:        domain.ChainBase,
		Status:       domain.StatusOpening,
		Tier:         domain.TierC,
		AmountUSD:    domain.MustDecimal("10"),
		OpenTxHash:   txHash,
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, position))
	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "mint-open-stuck-revert",
			Chain:    domain.ChainBase,
			From:     zeroEVMAddress(),
			To:       domain.MustParseAddress(cfg.Execution.NPMBaseAddress),
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxStuck,
	}))

	source := &fakeBaseReceiptSource{receipts: map[string]*types.Receipt{
		common.HexToHash(txHash).Hex(): {
			TxHash:      common.HexToHash(txHash),
			Status:      types.ReceiptStatusFailed,
			BlockNumber: newTestBigInt(102),
			BlockHash:   common.HexToHash("0x3"),
		},
	}}

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, source, nil, time.Now()))

	tx, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.TxReverted, tx.Status)

	updated, err := store.PositionRepo().FindByID(ctx, position.ID)
	require.NoError(t, err)
	require.Equal(t, domain.StatusRejected, updated.Status)
}

func TestReconcileBasePendingTxs_TimeoutMarksSubmittedPrivateAsStuck(t *testing.T) {
	store := newLiveReconcileTestStore(t)
	ctx := context.Background()
	cfg := liveReconcileTestConfig()
	cfg.Execution.SendTimeoutSeconds = 1
	txHash := "0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "mint-stuck-1",
			Chain:    domain.ChainBase,
			From:     zeroEVMAddress(),
			To:       domain.MustParseAddress(cfg.Execution.NPMBaseAddress),
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxSubmittedPrivate,
	}))
	markSQLiteBroadcastAtOld(t, store, txHash, time.Now().Add(-5*time.Second).UnixMilli())

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, &fakeBaseReceiptSource{}, nil, time.Now()))

	tx, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.TxStuck, tx.Status)
}

func TestReconcileBasePendingTxs_CollectReceiptClosesExitingPosition(t *testing.T) {
	store := newLiveReconcileTestStore(t)
	ctx := context.Background()
	cfg := liveReconcileTestConfig()
	txHash := "0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
	wallet := domain.MustParseAddress("0x4444444444444444444444444444444444444444")

	position := &domain.Position{
		ID:           "pos-exit-1",
		TokenID:      "123",
		PoolID:       "0x5555555555555555555555555555555555555555",
		Chain:        domain.ChainBase,
		Status:       domain.StatusExiting,
		Tier:         domain.TierC,
		AmountUSD:    domain.MustDecimal("10"),
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Add(-time.Hour).Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, position))

	data := encodeLiveCloseCollectCalldata(newTestBigIntFromString("123"), common.HexToAddress(wallet.String()), newTestBigInt(1), newTestBigInt(1))
	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "collect-123",
			Chain:    domain.ChainBase,
			From:     wallet,
			To:       domain.MustParseAddress(cfg.Execution.NPMBaseAddress),
			Data:     data,
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxBroadcast,
	}))

	source := &fakeBaseReceiptSource{receipts: map[string]*types.Receipt{
		common.HexToHash(txHash).Hex(): {
			TxHash:      common.HexToHash(txHash),
			Status:      types.ReceiptStatusSuccessful,
			BlockNumber: newTestBigInt(202),
			BlockHash:   common.HexToHash("0x2"),
		},
	}}

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, source, nil, time.Now()))

	tx, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.TxConfirmed, tx.Status)

	updated, err := store.PositionRepo().FindByID(ctx, position.ID)
	require.NoError(t, err)
	require.Equal(t, domain.StatusClosed, updated.Status)
}

func TestReconcileBasePendingTxs_StuckRevertedExitingPositionBecomesExitFailed(t *testing.T) {
	store := newLiveReconcileTestStore(t)
	ctx := context.Background()
	cfg := liveReconcileTestConfig()
	txHash := "0xefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef"
	wallet := domain.MustParseAddress("0x4444444444444444444444444444444444444444")

	position := &domain.Position{
		ID:           "pos-exit-stuck-revert",
		TokenID:      "123",
		PoolID:       "0x5555555555555555555555555555555555555555",
		Chain:        domain.ChainBase,
		Status:       domain.StatusExiting,
		Tier:         domain.TierC,
		AmountUSD:    domain.MustDecimal("10"),
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Add(-time.Hour).Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, position))

	data := encodeLiveCloseCollectCalldata(newTestBigIntFromString("123"), common.HexToAddress(wallet.String()), newTestBigInt(1), newTestBigInt(1))
	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "collect-stuck-revert-123",
			Chain:    domain.ChainBase,
			From:     wallet,
			To:       domain.MustParseAddress(cfg.Execution.NPMBaseAddress),
			Data:     data,
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxStuck,
	}))

	source := &fakeBaseReceiptSource{receipts: map[string]*types.Receipt{
		common.HexToHash(txHash).Hex(): {
			TxHash:      common.HexToHash(txHash),
			Status:      types.ReceiptStatusFailed,
			BlockNumber: newTestBigInt(203),
			BlockHash:   common.HexToHash("0x4"),
		},
	}}

	require.NoError(t, reconcileBasePendingTxs(ctx, cfg, store, source, nil, time.Now()))

	tx, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, txHash)
	require.NoError(t, err)
	require.Equal(t, domain.TxReverted, tx.Status)

	updated, err := store.PositionRepo().FindByID(ctx, position.ID)
	require.NoError(t, err)
	require.Equal(t, domain.StatusExitFailed, updated.Status)
}

func newLiveReconcileTestStore(t *testing.T) *sqlite.Store {
	t.Helper()
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "live_reconcile.sqlite"))
	require.NoError(t, err)
	return store
}

func liveReconcileTestConfig() *config.Config {
	return &config.Config{
		Store: config.Store{
			Backend:    "sqlite",
			SQLitePath: ":memory:",
		},
		Chains: config.Chains{
			Base: config.ChainConfig{
				Confirmations: 1,
			},
		},
		Execution: config.Execution{
			NPMBaseAddress:      "0x8888888888888888888888888888888888888888",
			SendTimeoutSeconds:  180,
			TxDeadlineSeconds:   300,
			ExitDeadlineSeconds: 600,
		},
	}
}

func mintReceiptFixture(t *testing.T, txHash common.Hash, npm common.Address, wallet string, tokenID string, liquidity string, amount0 string, amount1 string) *types.Receipt {
	t.Helper()
	token := newTestBigIntFromString(tokenID)
	liq := newTestBigIntFromString(liquidity)
	amt0 := newTestBigIntFromString(amount0)
	amt1 := newTestBigIntFromString(amount1)
	data := make([]byte, 96)
	copy(data[32-len(liq.Bytes()):32], liq.Bytes())
	copy(data[64-len(amt0.Bytes()):64], amt0.Bytes())
	copy(data[96-len(amt1.Bytes()):96], amt1.Bytes())
	return &types.Receipt{
		TxHash:      txHash,
		Status:      types.ReceiptStatusSuccessful,
		BlockNumber: newTestBigInt(100),
		BlockHash:   common.HexToHash("0xabc"),
		Logs: []*types.Log{
			{
				Address: npm,
				Topics: []common.Hash{
					erc721TransferTopic,
					zeroTopic,
					addressToTopic(common.HexToAddress(wallet)),
					bigIntToTopic(token),
				},
			},
			{
				Address: npm,
				Topics: []common.Hash{
					npmIncreaseLiquidityTopic,
					bigIntToTopic(token),
				},
				Data: data,
			},
		},
	}
}

func markSQLiteBroadcastAtOld(t *testing.T, store *sqlite.Store, txHash string, old int64) {
	t.Helper()
	db := extractSQLiteDB(t, store)
	_, err := db.Exec(`UPDATE live_reconcile_transactions SET broadcast_at = ? WHERE tx_hash = ?`, old, txHash)
	require.NoError(t, err)
}

func extractSQLiteDB(t *testing.T, store *sqlite.Store) *sql.DB {
	t.Helper()
	type dbStore interface {
		DB() *sql.DB
	}
	typed, ok := any(store).(dbStore)
	require.True(t, ok)
	return typed.DB()
}

func newTestBigInt(value int64) *big.Int {
	return big.NewInt(value)
}

func newTestBigIntFromString(value string) *big.Int {
	n, ok := new(big.Int).SetString(value, 10)
	if !ok {
		panic("invalid test big int")
	}
	return n
}
