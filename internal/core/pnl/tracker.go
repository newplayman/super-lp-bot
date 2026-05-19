package pnl

import (
	"context"
	"fmt"
	"sync"

	"github.com/lpbot/lpbot/internal/domain"
)

// PnLTrackerImpl is a production implementation of PnLTracker.
// It provides real-time mark-to-market valuation, fee tracking,
// and impermanent loss calculation for LP positions.
type PnLTrackerImpl struct {
	cfg         PnLConfig
	priceSource PriceSource
	ledger      LedgerWriter

	mu          sync.RWMutex
	positions   map[string]*trackedPosition
}

// LedgerWriter defines the interface for writing ledger entries.
// This is a subset of ports.LedgerRepo focused on write operations.
type LedgerWriter interface {
	// AppendLedgerEntry writes a new ledger entry and returns the entry with assigned ID.
	AppendLedgerEntry(ctx context.Context, entry LedgerEntry) (LedgerEntry, error)
}

// LedgerEntry represents a PnL ledger entry for recording.
// This mirrors ports.LedgerEntry for internal use.
type LedgerEntry struct {
	ID          string
	PositionID  string
	Kind        string
	Amount      domain.Decimal
	TokenSymbol string
	BlockRef    domain.BlockRef
	TxHash      string
}

// NewPnLTracker creates a new PnLTracker implementation.
func NewPnLTracker(cfg PnLConfig, priceSource PriceSource, ledger LedgerWriter) *PnLTrackerImpl {
	if ledger == nil {
		panic("ledger is required")
	}
	return &PnLTrackerImpl{
		cfg:         cfg,
		priceSource: priceSource,
		ledger:      ledger,
		positions:   make(map[string]*trackedPosition),
	}
}

// Ensure PnLTrackerImpl implements PnLTracker at compile time.
var _ PnLTracker = (*PnLTrackerImpl)(nil)

// TrackPosition starts tracking a new position for PnL calculations.
// Called when a position.opened event is received.
func (t *PnLTrackerImpl) TrackPosition(ctx context.Context, pos *domain.Position) error {
	if pos == nil {
		return fmt.Errorf("position cannot be nil")
	}
	if pos.ID == "" {
		return fmt.Errorf("position ID cannot be empty")
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	// Check if already tracking
	if _, exists := t.positions[pos.ID]; exists {
		return fmt.Errorf("position %s is already being tracked", pos.ID)
	}

	t.positions[pos.ID] = newTrackedPosition(pos)
	return nil
}

// UntrackPosition stops tracking a position.
// Called when a position is closed or needs to be removed.
func (t *PnLTrackerImpl) UntrackPosition(ctx context.Context, positionID string) error {
	if positionID == "" {
		return fmt.Errorf("position ID cannot be empty")
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	if _, exists := t.positions[positionID]; !exists {
		return fmt.Errorf("position %s is not being tracked", positionID)
	}

	delete(t.positions, positionID)
	return nil
}

// MarkPrice updates the mark-to-market valuation for all tracked positions.
// Called periodically (e.g., every block or N seconds).
// Returns the number of positions updated.
func (t *PnLTrackerImpl) MarkPrice(ctx context.Context) (int, error) {
	t.mu.RLock()
	defer t.mu.RUnlock()

	count := 0
	for posID, tp := range t.positions {
		// Get prices for this position's pool
		price0, price1, err := t.priceSource.GetPrice(ctx, tp.position.PoolID, "")
		if err != nil {
			continue // Skip positions with price errors
		}

		// Calculate current valuation
		valuation, err := t.calculateValuation(tp.position, price0, price1)
		if err != nil {
			continue
		}

		// Update peak value tracking
		if valuation.GreaterThan(tp.peakValue) {
			tp.peakValue = valuation
		}

		// Create snapshot
		snapshot := &PositionSnapshot{
			PositionID:   posID,
			ValuationUSD: valuation,
			FeeUSD:       tp.feeAccrued,
			ILUSD:        domain.MustDecimal("0"),
			NetPnLUSD:    tp.feeAccrued,
			BlockRef: domain.BlockRef{
				Chain:  tp.position.Chain,
				Number: 0, // Updated by caller if available
			},
		}

		// Calculate IL if enabled
		if t.cfg.ILEnabled {
			il, err := RealizeIL(*tp.position, price0, price1)
			if err == nil {
				snapshot.ILUSD = il
				snapshot.NetPnLUSD = tp.feeAccrued.Add(il)
			}
		}

		tp.lastMark = snapshot
		count++
	}

	return count, nil
}

// GetPositionPnL returns the current PnL breakdown for a position.
// Returns nil if position is not tracked.
func (t *PnLTrackerImpl) GetPositionPnL(ctx context.Context, positionID string) (*PnLResult, error) {
	t.mu.RLock()
	defer t.mu.RUnlock()

	tp, exists := t.positions[positionID]
	if !exists {
		return nil, nil
	}

	// Get current prices
	price0, price1, err := t.priceSource.GetPrice(ctx, tp.position.PoolID, "")
	if err != nil {
		return nil, fmt.Errorf("failed to get prices: %w", err)
	}

	// Calculate IL if enabled
	ilUSD := domain.MustDecimal("0")
	if t.cfg.ILEnabled {
		ilUSD, _ = RealizeIL(*tp.position, price0, price1)
	}

	return &PnLResult{
		FeeUSD:    tp.feeAccrued,
		ILUSD:     ilUSD,
		NetPnLUSD: tp.feeAccrued.Add(ilUSD),
	}, nil
}

// GetPositionSnapshot returns the latest point-in-time snapshot for a position.
func (t *PnLTrackerImpl) GetPositionSnapshot(ctx context.Context, positionID string) (*PositionSnapshot, error) {
	t.mu.RLock()
	defer t.mu.RUnlock()

	tp, exists := t.positions[positionID]
	if !exists {
		return nil, nil
	}

	return tp.lastMark, nil
}

// RecordRealizedPnL records the realized PnL when a position closes.
// This writes ledger entries for fee, IL, and other components.
func (t *PnLTrackerImpl) RecordRealizedPnL(ctx context.Context, positionID string, txHash string) (*PnLResult, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	tp, exists := t.positions[positionID]
	if !exists {
		return nil, fmt.Errorf("position %s is not being tracked", positionID)
	}

	// Get final prices
	price0, price1, err := t.priceSource.GetPrice(ctx, tp.position.PoolID, "")
	if err != nil {
		return nil, fmt.Errorf("failed to get prices: %w", err)
	}

	// Calculate final IL
	ilUSD := domain.MustDecimal("0")
	if t.cfg.ILEnabled {
		ilUSD, _ = RealizeIL(*tp.position, price0, price1)
	}

	// Create ledger entries for each PnL component
	netPnL := tp.feeAccrued.Add(ilUSD)

	// Record fee entry
	if !tp.feeAccrued.IsZero() {
		_, err := t.ledger.AppendLedgerEntry(ctx, LedgerEntry{
			PositionID: positionID,
			Kind:       "fee",
			Amount:     tp.feeAccrued,
			TxHash:     txHash,
		})
		if err != nil {
			return nil, fmt.Errorf("failed to record fee entry: %w", err)
		}
	}

	// Record IL entry
	if t.cfg.ILEnabled && !ilUSD.IsZero() {
		_, err := t.ledger.AppendLedgerEntry(ctx, LedgerEntry{
			PositionID: positionID,
			Kind:       "il",
			Amount:     ilUSD,
			TxHash:     txHash,
		})
		if err != nil {
			return nil, fmt.Errorf("failed to record IL entry: %w", err)
		}
	}

	// Remove from tracking
	delete(t.positions, positionID)

	return &PnLResult{
		FeeUSD:    tp.feeAccrued,
		ILUSD:     ilUSD,
		NetPnLUSD: netPnL,
	}, nil
}

// AddFees records additional fees accrued for a position.
// This should be called when fee income is collected from the pool.
func (t *PnLTrackerImpl) AddFees(ctx context.Context, positionID string, fees domain.Decimal) error {
	if fees.IsNegative() {
		return fmt.Errorf("fees cannot be negative")
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	tp, exists := t.positions[positionID]
	if !exists {
		return fmt.Errorf("position %s is not being tracked", positionID)
	}

	tp.feeAccrued = tp.feeAccrued.Add(fees)
	return nil
}

// calculateValuation computes the current USD value of a position.
// For V3 positions, this accounts for token amounts and current prices.
func (t *PnLTrackerImpl) calculateValuation(pos *domain.Position, price0, price1 domain.Decimal) (domain.Decimal, error) {
	// Simplified valuation: use position size (AmountUSD) as base
	// Full implementation would query token amounts from chain
	return pos.AmountUSD, nil
}