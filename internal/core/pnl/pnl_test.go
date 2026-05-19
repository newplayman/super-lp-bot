package pnl

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: PnLTracker must implement PnLTracker interface
var _ PnLTracker = (*defaultPnL)(nil)

// mockPriceSource is a mock implementation of PriceSource for testing.
type mockPriceSource struct {
	price0 domain.Decimal
	price1 domain.Decimal
	err    error
}

func (m *mockPriceSource) GetPrice(ctx context.Context, token0, token1 string) (domain.Decimal, domain.Decimal, error) {
	return m.price0, m.price1, m.err
}

// TestPnLResultConstants verifies PnLResult fields exist
func TestPnLResultConstants(t *testing.T) {
	result := PnLResult{
		FeeUSD:    domain.MustDecimal("100"),
		ILUSD:     domain.MustDecimal("-50"),
		NetPnLUSD: domain.MustDecimal("50"),
	}
	require.True(t, result.FeeUSD.IsPositive())
	require.True(t, result.ILUSD.IsNegative())
	require.Equal(t, domain.MustDecimal("50"), result.NetPnLUSD)
}

// TestPositionSnapshotFields verifies snapshot structure
func TestPositionSnapshotFields(t *testing.T) {
	snapshot := PositionSnapshot{
		PositionID:   "pos-123",
		ValuationUSD: domain.MustDecimal("1000"),
		FeeUSD:       domain.MustDecimal("50"),
		ILUSD:        domain.MustDecimal("-20"),
		NetPnLUSD:    domain.MustDecimal("30"),
		BlockRef: domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   12345678,
			Hash:     "0xabc123",
			TimeUnix: 1700000000,
		},
	}
	require.Equal(t, "pos-123", snapshot.PositionID)
	require.True(t, snapshot.ValuationUSD.GreaterThan(domain.Zero))
}

// TestPnLTrackerInterface defines the interface contract for PnLTracker.
// These tests verify that the interface is properly defined and can be used.
func TestPnLTrackerInterface(t *testing.T) {
	priceSource := &mockPriceSource{
		price0: domain.MustDecimal("2000"),
		price1: domain.MustDecimal("1"),
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
	ps := &mockPriceSource{price0: domain.MustDecimal("100"), price1: domain.MustDecimal("1")}
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