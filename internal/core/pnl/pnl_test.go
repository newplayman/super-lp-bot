package pnl

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: PnLTracker must implement PnLTracker interface
var _ PnLTracker = (*defaultPnL)(nil)

// mockPriceSource is a mock implementation of PriceSource for testing.
type mockPriceSource struct {
	price0 decimal.Decimal
	price1 decimal.Decimal
	err    error
}

func (m *mockPriceSource) GetPrice(ctx context.Context, token0, token1 string) (decimal.Decimal, decimal.Decimal, error) {
	return m.price0, m.price1, m.err
}

// TestPnLResultConstants verifies PnLResult fields exist
func TestPnLResultConstants(t *testing.T) {
	result := PnLResult{
		FeeUSD:    decimal.FromInt(100),
		ILUSD:     decimal.MustFromString("-50"),
		NetPnLUSD: decimal.FromInt(50),
	}
	require.True(t, result.FeeUSD.IsPositive())
	require.True(t, result.ILUSD.IsNeg())
	require.Equal(t, decimal.FromInt(50), result.NetPnLUSD)
}

// TestPositionSnapshotFields verifies snapshot structure
func TestPositionSnapshotFields(t *testing.T) {
	snapshot := PositionSnapshot{
		PositionID:   "pos-123",
		ValuationUSD: decimal.FromInt(1000),
		FeeUSD:       decimal.FromInt(50),
		ILUSD:        decimal.MustFromString("-20"),
		NetPnLUSD:    decimal.FromInt(30),
		BlockRef: domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   12345678,
			Hash:     "0xabc123",
			TimeUnix: 1700000000,
		},
	}
	require.Equal(t, "pos-123", snapshot.PositionID)
	require.True(t, snapshot.ValuationUSD.GreaterThan(decimal.Zero))
}

// TestPnLTrackerInterface defines the interface contract for PnLTracker.
// These tests verify that the interface is properly defined and can be used.
func TestPnLTrackerInterface(t *testing.T) {
	priceSource := &mockPriceSource{
		price0: decimal.FromInt(2000),
		price1: decimal.FromInt(1),
	}

	tracker := NewDefaultPnL(priceSource)
	require.NotNil(t, tracker)

	// Compile-time check: tracker must implement PnLTracker
	var _ PnLTracker = tracker
}

// TestMarkPricePanics verifies MarkPrice panics for Phase 0 stub
func TestMarkPricePanics(t *testing.T) {
	tracker := NewDefaultPnL(&mockPriceSource{})

	require.Panics(t, func() {
		_, _ = tracker.MarkPrice(context.Background())
	}, "MarkPrice should panic in Phase 0 stub")
}

// TestGetPositionPnLPanics verifies GetPositionPnL panics for Phase 0 stub
func TestGetPositionPnLPanics(t *testing.T) {
	tracker := NewDefaultPnL(&mockPriceSource{})

	require.Panics(t, func() {
		_, _ = tracker.GetPositionPnL(context.Background(), "pos-123")
	}, "GetPositionPnL should panic in Phase 0 stub")
}

// TestGetPositionSnapshotPanics verifies GetPositionSnapshot panics for Phase 0 stub
func TestGetPositionSnapshotPanics(t *testing.T) {
	tracker := NewDefaultPnL(&mockPriceSource{})

	require.Panics(t, func() {
		_, _ = tracker.GetPositionSnapshot(context.Background(), "pos-123")
	}, "GetPositionSnapshot should panic in Phase 0 stub")
}

// TestRecordRealizedPnLPanics verifies RecordRealizedPnL panics for Phase 0 stub
func TestRecordRealizedPnLPanics(t *testing.T) {
	tracker := NewDefaultPnL(&mockPriceSource{})

	require.Panics(t, func() {
		_, _ = tracker.RecordRealizedPnL(context.Background(), "pos-123", "0xtxhash")
	}, "RecordRealizedPnL should panic in Phase 0 stub")
}

// TestTrackPositionPanics verifies TrackPosition panics for Phase 0 stub
func TestTrackPositionPanics(t *testing.T) {
	tracker := NewDefaultPnL(&mockPriceSource{})

	pos := &domain.Position{
		ID:     "pos-123",
		PoolID: "pool-456",
		Chain:  domain.ChainBase,
		Status: domain.StatusOpen,
	}

	require.Panics(t, func() {
		_ = tracker.TrackPosition(context.Background(), pos)
	}, "TrackPosition should panic in Phase 0 stub")
}

// TestUntrackPositionPanics verifies UntrackPosition panics for Phase 0 stub
func TestUntrackPositionPanics(t *testing.T) {
	tracker := NewDefaultPnL(&mockPriceSource{})

	require.Panics(t, func() {
		_ = tracker.UntrackPosition(context.Background(), "pos-123")
	}, "UntrackPosition should panic in Phase 0 stub")
}

// TestNewDefaultPnLCreation verifies constructor works
func TestNewDefaultPnLCreation(t *testing.T) {
	ps := &mockPriceSource{price0: decimal.FromInt(100), price1: decimal.FromInt(1)}
	tracker := NewDefaultPnL(ps)
	require.NotNil(t, tracker)
}

// TestPnLTrackerWithNilPriceSource verifies tracker works with nil price source
func TestPnLTrackerWithNilPriceSource(t *testing.T) {
	tracker := NewDefaultPnL(nil)
	require.NotNil(t, tracker)
	// Still should panic on operations
	require.Panics(t, func() {
		_, _ = tracker.MarkPrice(context.Background())
	})
}