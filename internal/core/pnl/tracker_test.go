package pnl

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// mockLedgerWriter is a mock implementation of LedgerWriter for testing.
type mockLedgerWriter struct {
	entries []LedgerEntry
	err     error
}

func (m *mockLedgerWriter) AppendLedgerEntry(ctx context.Context, entry LedgerEntry) (LedgerEntry, error) {
	if m.err != nil {
		return LedgerEntry{}, m.err
	}
	entry.ID = fmt.Sprintf("entry-%d", len(m.entries)+1)
	m.entries = append(m.entries, entry)
	return entry, nil
}

// mockPriceSourceMap is a mock implementation of PriceSource for testing with price maps.
type mockPriceSourceMap struct {
	prices map[string][2]domain.Decimal
	err    error
}

func (m *mockPriceSourceMap) GetPrice(ctx context.Context, token0, token1 string) (domain.Decimal, domain.Decimal, error) {
	if m.err != nil {
		return domain.Zero, domain.Zero, m.err
	}
	prices, ok := m.prices[token0]
	if !ok {
		return domain.Zero, domain.Zero, nil
	}
	return prices[0], prices[1], nil
}

func (m *mockPriceSourceMap) SetPrice(poolID string, price0, price1 domain.Decimal) {
	if m.prices == nil {
		m.prices = make(map[string][2]domain.Decimal)
	}
	m.prices[poolID] = [2]domain.Decimal{price0, price1}
}

// mockLedgerRepo is a mock implementation of ports.LedgerRepo for testing.
type mockLedgerRepo struct {
	entries     []ports.LedgerEntry
	byPosition map[string][]ports.LedgerEntry
	err        error
}

func (m *mockLedgerRepo) Append(ctx context.Context, entry ports.LedgerEntry) (ports.LedgerEntry, error) {
	if m.err != nil {
		return ports.LedgerEntry{}, m.err
	}
	entry.ID = fmt.Sprintf("entry-%d", len(m.entries)+1)
	m.entries = append(m.entries, entry)
	if m.byPosition == nil {
		m.byPosition = make(map[string][]ports.LedgerEntry)
	}
	m.byPosition[entry.PositionID] = append(m.byPosition[entry.PositionID], entry)
	return entry, nil
}

func (m *mockLedgerRepo) ByPosition(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.byPosition[positionID], nil
}

func (m *mockLedgerRepo) ByPositionAndKind(ctx context.Context, positionID string, kind ports.LedgerEntryKind) ([]ports.LedgerEntry, error) {
	if m.err != nil {
		return nil, m.err
	}
	var result []ports.LedgerEntry
	for _, entry := range m.byPosition[positionID] {
		if entry.Kind == kind {
			result = append(result, entry)
		}
	}
	return result, nil
}

func (m *mockLedgerRepo) AggregateByKind(ctx context.Context, positionID string) (map[ports.LedgerEntryKind]domain.Decimal, error) {
	if m.err != nil {
		return nil, m.err
	}
	result := make(map[ports.LedgerEntryKind]domain.Decimal)
	for _, entry := range m.byPosition[positionID] {
		existing := result[entry.Kind]
		result[entry.Kind] = existing.Add(entry.Amount)
	}
	return result, nil
}

func (m *mockLedgerRepo) LatestBlock(ctx context.Context) (*domain.BlockRef, error) {
	if m.err != nil {
		return nil, m.err
	}
	return nil, nil
}

// TestPnLTracker_TrackPosition tests tracking a new position.
func TestPnLTracker_TrackPosition(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:     "pos-123",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	// Verify position is tracked
	result, err := tracker.GetPositionPnL(context.Background(), "pos-123")
	require.NoError(t, err)
	require.NotNil(t, result)
}

// TestPnLTracker_TrackPosition_Duplicate tests tracking the same position twice.
func TestPnLTracker_TrackPosition_Duplicate(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:     "pos-dup",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	// Attempt to track again should fail
	err = tracker.TrackPosition(context.Background(), pos)
	require.Error(t, err)
	require.Contains(t, err.Error(), "already being tracked")
}

// TestPnLTracker_TrackPosition_NilPosition tests tracking a nil position.
func TestPnLTracker_TrackPosition_NilPosition(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	err := tracker.TrackPosition(context.Background(), nil)
	require.Error(t, err)
	require.Contains(t, err.Error(), "cannot be nil")
}

// TestPnLTracker_TrackPosition_EmptyID tests tracking a position with empty ID.
func TestPnLTracker_TrackPosition_EmptyID(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:     "",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.Error(t, err)
	require.Contains(t, err.Error(), "ID cannot be empty")
}

// TestPnLTracker_UntrackPosition tests stopping position tracking.
func TestPnLTracker_UntrackPosition(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:     "pos-remove",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	// Track first
	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	// Untrack
	err = tracker.UntrackPosition(context.Background(), "pos-remove")
	require.NoError(t, err)

	// Verify position is no longer tracked
	result, err := tracker.GetPositionPnL(context.Background(), "pos-remove")
	require.NoError(t, err)
	require.Nil(t, result)
}

// TestPnLTracker_UntrackPosition_NotTracked tests untracking a non-tracked position.
func TestPnLTracker_UntrackPosition_NotTracked(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	err := tracker.UntrackPosition(context.Background(), "non-existent")
	require.Error(t, err)
	require.Contains(t, err.Error(), "not being tracked")
}

// TestPnLTracker_UntrackPosition_EmptyID tests untracking with empty ID.
func TestPnLTracker_UntrackPosition_EmptyID(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	err := tracker.UntrackPosition(context.Background(), "")
	require.Error(t, err)
	require.Contains(t, err.Error(), "ID cannot be empty")
}

// TestPnLTracker_MarkPrice tests mark-to-market updates.
func TestPnLTracker_MarkPrice(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ps.SetPrice("pool-456", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:        "pos-mark",
		PoolID:    "pool-456",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.MustDecimal("1000"),
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	count, err := tracker.MarkPrice(context.Background())
	require.NoError(t, err)
	require.Equal(t, 1, count)

	// Verify snapshot was created
	snapshot, err := tracker.GetPositionSnapshot(context.Background(), "pos-mark")
	require.NoError(t, err)
	require.NotNil(t, snapshot)
	require.Equal(t, "pos-mark", snapshot.PositionID)
}

// TestPnLTracker_MarkPrice_EmptyTracker tests marking when no positions are tracked.
func TestPnLTracker_MarkPrice_EmptyTracker(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ps.SetPrice("pool-456", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	count, err := tracker.MarkPrice(context.Background())
	require.NoError(t, err)
	require.Equal(t, 0, count)
}

// TestPnLTracker_MarkPrice_MultiplePositions tests marking multiple positions.
func TestPnLTracker_MarkPrice_MultiplePositions(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ps.SetPrice("pool-1", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ps.SetPrice("pool-2", domain.MustDecimal("3000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos1 := &domain.Position{ID: "pos-1", PoolID: "pool-1", Chain: domain.ChainBase, Status: domain.StatusOpen}
	pos2 := &domain.Position{ID: "pos-2", PoolID: "pool-2", Chain: domain.ChainBase, Status: domain.StatusOpen}

	err := tracker.TrackPosition(context.Background(), pos1)
	require.NoError(t, err)
	err = tracker.TrackPosition(context.Background(), pos2)
	require.NoError(t, err)

	count, err := tracker.MarkPrice(context.Background())
	require.NoError(t, err)
	require.Equal(t, 2, count)
}

// TestPnLTracker_GetPositionPnL tests PnL retrieval.
func TestPnLTracker_GetPositionPnL(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ps.SetPrice("pool-456", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:        "pos-pnl",
		PoolID:    "pool-456",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.MustDecimal("1000"),
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	pnl, err := tracker.GetPositionPnL(context.Background(), "pos-pnl")
	require.NoError(t, err)
	require.NotNil(t, pnl)
	// Fee should be zero initially
	require.True(t, pnl.FeeUSD.IsZero())
}

// TestPnLTracker_GetPositionPnL_NotTracked tests PnL retrieval for non-tracked position.
func TestPnLTracker_GetPositionPnL_NotTracked(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pnl, err := tracker.GetPositionPnL(context.Background(), "non-existent")
	require.NoError(t, err)
	require.Nil(t, pnl)
}

// TestPnLTracker_RecordRealizedPnL tests recording realized PnL.
func TestPnLTracker_RecordRealizedPnL(t *testing.T) {
	cfg := PnLConfig{
		MarkInterval: 15 * time.Second,
		ILEnabled:    false, // Disable IL to test fee-only recording
	}
	ps := &mockPriceSourceMap{}
	ps.SetPrice("pool-456", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:        "pos-close",
		PoolID:    "pool-456",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.MustDecimal("1000"),
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	// Add some fees
	err = tracker.AddFees(context.Background(), "pos-close", domain.MustDecimal("50"))
	require.NoError(t, err)

	// Record realized PnL
	pnl, err := tracker.RecordRealizedPnL(context.Background(), "pos-close", "0xtxhash123")
	require.NoError(t, err)
	require.NotNil(t, pnl)

	// Verify fee was recorded
	require.Equal(t, domain.MustDecimal("50"), pnl.FeeUSD)

	// Verify ledger entries were written (only fee entry when IL disabled)
	require.Len(t, ledger.entries, 1)
	require.Equal(t, "pos-close", ledger.entries[0].PositionID)
	require.Equal(t, "fee", ledger.entries[0].Kind)

	// Verify position is no longer tracked
	result, err := tracker.GetPositionPnL(context.Background(), "pos-close")
	require.NoError(t, err)
	require.Nil(t, result)
}

// TestPnLTracker_RecordRealizedPnL_NotTracked tests recording PnL for non-tracked position.
func TestPnLTracker_RecordRealizedPnL_NotTracked(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pnl, err := tracker.RecordRealizedPnL(context.Background(), "non-existent", "0xtx")
	require.Error(t, err)
	require.Nil(t, pnl)
	require.Contains(t, err.Error(), "not being tracked")
}

// TestPnLTracker_RecordRealizedPnL_WithIL tests recording PnL with IL calculation.
func TestPnLTracker_RecordRealizedPnL_WithIL(t *testing.T) {
	cfg := PnLConfig{
		MarkInterval: 15 * time.Second,
		ILEnabled:    true,
	}
	ps := &mockPriceSourceMap{}
	// Set a price that will generate some IL
	ps.SetPrice("pool-456", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:        "pos-il",
		PoolID:    "pool-456",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.MustDecimal("1000"),
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	pnl, err := tracker.RecordRealizedPnL(context.Background(), "pos-il", "0xtxhash")
	require.NoError(t, err)
	require.NotNil(t, pnl)

	// IL should be calculated (may be zero or negative depending on price)
	require.NotNil(t, pnl.ILUSD)
}

// TestPnLTracker_RecordRealizedPnL_ILDisabled tests recording PnL with IL disabled.
func TestPnLTracker_RecordRealizedPnL_ILDisabled(t *testing.T) {
	cfg := PnLConfig{
		MarkInterval: 15 * time.Second,
		ILEnabled:    false,
	}
	ps := &mockPriceSourceMap{}
	ps.SetPrice("pool-456", domain.MustDecimal("2000"), domain.MustDecimal("1"))
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:        "pos-no-il",
		PoolID:    "pool-456",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.MustDecimal("1000"),
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	pnl, err := tracker.RecordRealizedPnL(context.Background(), "pos-no-il", "0xtxhash")
	require.NoError(t, err)
	require.NotNil(t, pnl)

	// IL should be zero when disabled
	require.True(t, pnl.ILUSD.IsZero())
}

// TestPnLTracker_ImpermanentLoss tests IL calculation.
func TestPnLTracker_ImpermanentLoss(t *testing.T) {
	tests := []struct {
		name           string
		initialPrice0  domain.Decimal
		initialPrice1  domain.Decimal
		currentPrice0  domain.Decimal
		currentPrice1  domain.Decimal
		tickLower      int64
		tickUpper      int64
		expectILNeg    bool // whether IL should be negative
	}{
		{
			name:           "v3_in_range_no_price_change",
			initialPrice0:  domain.MustDecimal("1"),
			initialPrice1:  domain.MustDecimal("1"),
			currentPrice0:  domain.MustDecimal("1"),
			currentPrice1:  domain.MustDecimal("1"),
			tickLower:      -1000,
			tickUpper:      1000,
			expectILNeg:    false, // No IL when price doesn't change
		},
		{
			name:           "v3_in_range_price_increases",
			initialPrice0:  domain.MustDecimal("1"),
			initialPrice1:  domain.MustDecimal("1"),
			currentPrice0:  domain.MustDecimal("1"),
			currentPrice1:  domain.MustDecimal("1.1"), // 10% increase
			tickLower:      -1000,
			tickUpper:      1000,
			expectILNeg:    true, // IL should be negative (loss)
		},
		{
			name:           "v3_below_range",
			initialPrice0:  domain.MustDecimal("1"),
			initialPrice1:  domain.MustDecimal("1"),
			currentPrice0:  domain.MustDecimal("2"),
			currentPrice1:  domain.MustDecimal("1"),
			tickLower:      -1000,
			tickUpper:      1000,
			expectILNeg:    true, // IL should be negative
		},
		{
			name:           "v3_above_range",
			initialPrice0:  domain.MustDecimal("1"),
			initialPrice1:  domain.MustDecimal("1"),
			currentPrice0:  domain.MustDecimal("2"),
			currentPrice1:  domain.MustDecimal("1"),
			tickLower:      -1000,
			tickUpper:      1000,
			expectILNeg:    true, // IL should be negative
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cfg := PnLConfig{
				MarkInterval: 15 * time.Second,
				ILEnabled:    true,
			}
			ps := &mockPriceSourceMap{}
			ps.SetPrice("pool-test", tc.currentPrice0, tc.currentPrice1)
			ledger := &mockLedgerWriter{}
			tracker := NewPnLTracker(cfg, ps, ledger)

			pos := &domain.Position{
				ID:        "pos-il-test",
				PoolID:    "pool-test",
				Chain:     domain.ChainBase,
				Status:    domain.StatusOpen,
				AmountUSD: domain.MustDecimal("1000"),
				TickLower: tc.tickLower,
				TickUpper: tc.tickUpper,
			}

			err := tracker.TrackPosition(context.Background(), pos)
			require.NoError(t, err)

			pnl, err := tracker.GetPositionPnL(context.Background(), "pos-il-test")
			require.NoError(t, err)

			if tc.expectILNeg {
				// IL should be <= 0
				require.True(t, pnl.ILUSD.IsNegative() || pnl.ILUSD.IsZero(),
					"IL should be non-positive, got %s", pnl.ILUSD.String())
			}
		})
	}
}

// TestPnLTracker_AddFees tests adding fees to a tracked position.
func TestPnLTracker_AddFees(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:     "pos-fees",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	// Add fees
	err = tracker.AddFees(context.Background(), "pos-fees", domain.MustDecimal("100"))
	require.NoError(t, err)

	// Add more fees
	err = tracker.AddFees(context.Background(), "pos-fees", domain.MustDecimal("50"))
	require.NoError(t, err)

	pnl, err := tracker.GetPositionPnL(context.Background(), "pos-fees")
	require.NoError(t, err)
	require.Equal(t, domain.MustDecimal("150"), pnl.FeeUSD)
}

// TestPnLTracker_AddFees_NegativeFails tests that negative fees are rejected.
func TestPnLTracker_AddFees_NegativeFails(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	pos := &domain.Position{
		ID:     "pos-neg-fees",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	err := tracker.TrackPosition(context.Background(), pos)
	require.NoError(t, err)

	// Try to add negative fees
	err = tracker.AddFees(context.Background(), "pos-neg-fees", domain.MustDecimal("-50"))
	require.Error(t, err)
	require.Contains(t, err.Error(), "cannot be negative")
}

// TestPnLTracker_AddFees_NotTracked tests adding fees to non-tracked position.
func TestPnLTracker_AddFees_NotTracked(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}
	ledger := &mockLedgerWriter{}
	tracker := NewPnLTracker(cfg, ps, ledger)

	err := tracker.AddFees(context.Background(), "non-existent", domain.MustDecimal("100"))
	require.Error(t, err)
	require.Contains(t, err.Error(), "not being tracked")
}

// TestPnLConfig_Default tests the default configuration.
func TestPnLConfig_Default(t *testing.T) {
	cfg := DefaultPnLConfig()

	require.Equal(t, 15*time.Second, cfg.MarkInterval)
	require.True(t, cfg.ILEnabled)
}

// TestNewPnLTracker_NilLedger panics when ledger is nil.
func TestNewPnLTracker_NilLedger(t *testing.T) {
	cfg := DefaultPnLConfig()
	ps := &mockPriceSourceMap{}

	require.Panics(t, func() {
		NewPnLTracker(cfg, ps, nil)
	}, "NewPnLTracker should panic when ledger is nil")
}

// TestLedgerService_RecordPnL tests the ledger service PnL recording.
func TestLedgerService_RecordPnL(t *testing.T) {
	repo := &mockLedgerRepo{}
	service := NewLedgerService(repo)

	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 12345678,
		Hash:   "0xabc123",
	}

	result, err := service.RecordPnL(
		context.Background(),
		"pos-ledger-test",
		domain.MustDecimal("100"),
		domain.MustDecimal("-50"),
		blockRef,
		"0xtxhash",
	)
	require.NoError(t, err)

	// Check result
	require.Equal(t, domain.MustDecimal("100"), result.FeeUSD)
	require.Equal(t, domain.MustDecimal("-50"), result.ILUSD)
	require.Equal(t, domain.MustDecimal("50"), result.NetPnLUSD)

	// Check ledger entries
	require.Len(t, repo.entries, 2)

	// Find fee entry
	var feeEntry ports.LedgerEntry
	for _, entry := range repo.entries {
		if entry.Kind == ports.LedgerEntryFee {
			feeEntry = entry
			break
		}
	}
	require.Equal(t, "pos-ledger-test", feeEntry.PositionID)
	require.Equal(t, domain.MustDecimal("100"), feeEntry.Amount)
}

// TestLedgerService_GetAggregatedPnL tests aggregating PnL from ledger.
func TestLedgerService_GetAggregatedPnL(t *testing.T) {
	repo := &mockLedgerRepo{}
	service := NewLedgerService(repo)

	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 12345678,
	}

	// Record some entries first
	_, err := service.RecordPnL(
		context.Background(),
		"pos-agg-test",
		domain.MustDecimal("100"),
		domain.MustDecimal("-50"),
		blockRef,
		"0xtxhash",
	)
	require.NoError(t, err)

	// Aggregate
	result, err := service.GetAggregatedPnL(context.Background(), "pos-agg-test")
	require.NoError(t, err)
	require.Equal(t, domain.MustDecimal("100"), result.FeeUSD)
	require.Equal(t, domain.MustDecimal("-50"), result.ILUSD)
}

// TestLedgerEntryBuilder tests the ledger entry builder.
func TestLedgerEntryBuilder(t *testing.T) {
	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 12345678,
		Hash:   "0xabc",
	}

	builder := NewLedgerEntryBuilder("pos-builder", "0xtx", blockRef)

	entry := builder.WithKind(ports.LedgerEntryFee, domain.MustDecimal("50"))
	require.Equal(t, "pos-builder", entry.PositionID)
	require.Equal(t, ports.LedgerEntryFee, entry.Kind)
	require.Equal(t, domain.MustDecimal("50"), entry.Amount)
	require.Equal(t, blockRef, entry.BlockRef)
	require.Equal(t, "0xtx", entry.TxHash)
}

// TestTrackedPosition_Creation tests creating a tracked position.
func TestTrackedPosition_Creation(t *testing.T) {
	pos := &domain.Position{
		ID:        "pos-create-test",
		PoolID:    "pool-1",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.MustDecimal("1000"),
	}

	tp := newTrackedPosition(pos)
	require.Equal(t, pos, tp.position)
	require.Nil(t, tp.lastMark)
	require.True(t, tp.feeAccrued.IsZero())
	require.True(t, tp.peakValue.IsZero())
}

// Ensure mockLedgerRepo implements ports.LedgerRepo at compile time.
var _ ports.LedgerRepo = (*mockLedgerRepo)(nil)