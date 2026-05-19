package ports

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

// Compile-time interface compliance check for LedgerRepo.
// This ensures that any implementation satisfies the full interface contract.
var _ LedgerRepo = (*ledgerRepoNop)(nil)

// ledgerRepoNop is a no-op implementation for compile-time interface checks.
// It satisfies LedgerRepo for testing purposes.
type ledgerRepoNop struct{}

func (n *ledgerRepoNop) Append(_ context.Context, entry LedgerEntry) (LedgerEntry, error) {
	return entry, nil
}

func (n *ledgerRepoNop) ByPosition(_ context.Context, positionID string) ([]LedgerEntry, error) {
	return nil, nil
}

func (n *ledgerRepoNop) ByPositionAndKind(_ context.Context, positionID string, kind LedgerEntryKind) ([]LedgerEntry, error) {
	return nil, nil
}

func (n *ledgerRepoNop) AggregateByKind(_ context.Context, positionID string) (map[LedgerEntryKind]domain.Decimal, error) {
	return nil, nil
}

func (n *ledgerRepoNop) LatestBlock(_ context.Context) (*domain.BlockRef, error) {
	return nil, nil
}

// TestLedgerRepoInterface verifies the LedgerRepo interface is properly defined.
func TestLedgerRepoInterface(t *testing.T) {
	// LedgerRepo interface must exist and be implementable
	var repo LedgerRepo = &ledgerRepoNop{}
	if repo == nil {
		t.Fatal("LedgerRepo interface should be implementable")
	}
}

// TestLedgerEntryKindConstants verifies the entry kind constants are defined.
func TestLedgerEntryKindConstants(t *testing.T) {
	kinds := []LedgerEntryKind{
		LedgerEntryFee,
		LedgerEntryIL,
		LedgerEntrySwap,
		LedgerEntryGas,
		LedgerEntrySlippage,
		LedgerEntryRug,
	}
	for _, k := range kinds {
		if k == "" {
			t.Error("LedgerEntryKind constant should not be empty")
		}
	}
}

// TestLedgerEntryStruct verifies LedgerEntry can be instantiated with required fields.
func TestLedgerEntryStruct(t *testing.T) {
	entry := LedgerEntry{
		ID:          "test-id",
		PositionID:  "pos-123",
		Kind:        LedgerEntryFee,
		Amount:      domain.MustDecimal("100.50"),
		TokenSymbol: "USDC",
		BlockRef:    domain.BlockRef{Chain: domain.ChainBase, Number: 12345678},
		TxHash:      "0xabc123",
	}
	if entry.ID == "" {
		t.Error("LedgerEntry.ID should be set")
	}
	if entry.PositionID == "" {
		t.Error("LedgerEntry.PositionID should be set")
	}
	if entry.Kind != LedgerEntryFee {
		t.Error("LedgerEntry.Kind should be LedgerEntryFee")
	}
	if entry.Amount.IsZero() {
		t.Error("LedgerEntry.Amount should be non-zero")
	}
}