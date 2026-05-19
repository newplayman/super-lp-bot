package pnl

import (
	"context"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// LedgerService handles writing PnL ledger entries.
// It converts internal PnL data to ledger entries and persists them.
type LedgerService struct {
	repo ports.LedgerRepo
}

// NewLedgerService creates a new ledger service.
func NewLedgerService(repo ports.LedgerRepo) *LedgerService {
	return &LedgerService{
		repo: repo,
	}
}

// RecordPnL writes all PnL components as ledger entries for a position.
// Returns the aggregated result.
func (s *LedgerService) RecordPnL(
	ctx context.Context,
	positionID string,
	feeUSD domain.Decimal,
	ilUSD domain.Decimal,
	blockRef domain.BlockRef,
	txHash string,
) (*PnLResult, error) {
	var entries []ports.LedgerEntry

	// Record fee entry (positive = income)
	if !feeUSD.IsZero() {
		entries = append(entries, ports.LedgerEntry{
			PositionID:  positionID,
			Kind:        ports.LedgerEntryFee,
			Amount:      feeUSD,
			BlockRef:    blockRef,
			TxHash:      txHash,
		})
	}

	// Record IL entry (negative = loss)
	if !ilUSD.IsZero() {
		entries = append(entries, ports.LedgerEntry{
			PositionID:  positionID,
			Kind:        ports.LedgerEntryIL,
			Amount:      ilUSD,
			BlockRef:    blockRef,
			TxHash:      txHash,
		})
	}

	// Append all entries
	for i := range entries {
		_, err := s.repo.Append(ctx, entries[i])
		if err != nil {
			return nil, fmt.Errorf("failed to append ledger entry: %w", err)
		}
	}

	return &PnLResult{
		FeeUSD:    feeUSD,
		ILUSD:     ilUSD,
		NetPnLUSD: feeUSD.Add(ilUSD),
	}, nil
}

// RecordSwapCost writes a swap cost entry to the ledger.
func (s *LedgerService) RecordSwapCost(
	ctx context.Context,
	positionID string,
	swapCostUSD domain.Decimal,
	blockRef domain.BlockRef,
	txHash string,
) error {
	entry := ports.LedgerEntry{
		PositionID: positionID,
		Kind:       ports.LedgerEntrySwap,
		Amount:     swapCostUSD.Neg(), // Costs are negative
		BlockRef:   blockRef,
		TxHash:     txHash,
	}
	_, err := s.repo.Append(ctx, entry)
	return err
}

// RecordGasCost writes a gas cost entry to the ledger.
func (s *LedgerService) RecordGasCost(
	ctx context.Context,
	positionID string,
	gasUSD domain.Decimal,
	blockRef domain.BlockRef,
	txHash string,
) error {
	entry := ports.LedgerEntry{
		PositionID: positionID,
		Kind:       ports.LedgerEntryGas,
		Amount:     gasUSD.Neg(), // Costs are negative
		BlockRef:   blockRef,
		TxHash:     txHash,
	}
	_, err := s.repo.Append(ctx, entry)
	return err
}

// GetPositionLedgerEntries retrieves all ledger entries for a position.
func (s *LedgerService) GetPositionLedgerEntries(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	return s.repo.ByPosition(ctx, positionID)
}

// GetAggregatedPnL computes the total PnL for a position by aggregating ledger entries.
func (s *LedgerService) GetAggregatedPnL(ctx context.Context, positionID string) (*PnLResult, error) {
	aggregates, err := s.repo.AggregateByKind(ctx, positionID)
	if err != nil {
		return nil, err
	}

	feeUSD := aggregates[ports.LedgerEntryFee]
	ilUSD := aggregates[ports.LedgerEntryIL]

	return &PnLResult{
		FeeUSD:    feeUSD,
		ILUSD:     ilUSD,
		NetPnLUSD: feeUSD.Add(ilUSD),
	}, nil
}

// LedgerEntryBuilder helps construct ledger entries with common fields.
type LedgerEntryBuilder struct {
	PositionID string
	TxHash    string
	BlockRef  domain.BlockRef
	Timestamp time.Time
}

// NewLedgerEntryBuilder creates a new builder with required fields.
func NewLedgerEntryBuilder(positionID, txHash string, blockRef domain.BlockRef) *LedgerEntryBuilder {
	return &LedgerEntryBuilder{
		PositionID: positionID,
		TxHash:     txHash,
		BlockRef:   blockRef,
		Timestamp:  time.Now(),
	}
}

// WithKind sets the entry kind and returns the ledger entry.
func (b *LedgerEntryBuilder) WithKind(kind ports.LedgerEntryKind, amount domain.Decimal) ports.LedgerEntry {
	return ports.LedgerEntry{
		PositionID: b.PositionID,
		Kind:       kind,
		Amount:     amount,
		BlockRef:   b.BlockRef,
		TxHash:     b.TxHash,
	}
}