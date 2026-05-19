// Package main provides the lpbot-backtest CLI for Phase 0 validation.
package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// WriteLedger writes the PnL ledger entries for a simulation result.
func WriteLedger(ctx context.Context, repo ports.LedgerRepo, result *SimulationResult) error {
	if repo == nil {
		return nil
	}

	// Write fee entries
	for i, snapshot := range result.Snapshots {
		blockRef := domain.BlockRef{
			Chain:    result.Position.Chain,
			Number:   snapshot.BlockNumber,
			Hash:     fmt.Sprintf("0x%x", snapshot.BlockNumber),
			TimeUnix: snapshot.Timestamp.Unix(),
		}

		entry := ports.LedgerEntry{
			ID:          fmt.Sprintf("%s_fee_%d", result.Position.ID, i),
			PositionID:  result.Position.ID,
			Kind:        ports.LedgerEntryFee,
			BlockRef:    blockRef,
			Amount:      snapshot.CumulativeFees,
			TokenSymbol: "USD",
		}

		_, err := repo.Append(ctx, entry)
		if err != nil {
			return fmt.Errorf("append fee entry: %w", err)
		}
	}

	// Write IL entries
	for i, snapshot := range result.Snapshots {
		if snapshot.IL.IsZero() {
			continue
		}

		blockRef := domain.BlockRef{
			Chain:    result.Position.Chain,
			Number:   snapshot.BlockNumber,
			Hash:     fmt.Sprintf("0x%x", snapshot.BlockNumber),
			TimeUnix: snapshot.Timestamp.Unix(),
		}

		entry := ports.LedgerEntry{
			ID:          fmt.Sprintf("%s_il_%d", result.Position.ID, i),
			PositionID:  result.Position.ID,
			Kind:        ports.LedgerEntryIL,
			BlockRef:    blockRef,
			Amount:      snapshot.IL,
			TokenSymbol: "USD",
		}

		_, err := repo.Append(ctx, entry)
		if err != nil {
			return fmt.Errorf("append IL entry: %w", err)
		}
	}

	return nil
}