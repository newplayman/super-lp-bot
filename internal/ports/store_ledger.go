// Package ports defines the hexagonal architecture port interfaces.
//
// Ports are the contracts between the core business logic and external
// adapters. Core packages depend only on these interfaces, never on
// concrete adapter implementations.
//
// Store ports (this file):
//
//   - LedgerRepo: append-only PnL ledger for fee/IL/swap/gas/slippage/rug tracking
//
// See spec §4.4 for Repository design and §4.2 for pnl_ledger table schema.
package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// LedgerEntryKind categorizes the type of PnL entry for aggregation and reporting.
type LedgerEntryKind string

const (
	LedgerEntryFee       LedgerEntryKind = "fee"
	LedgerEntryIL        LedgerEntryKind = "il"
	LedgerEntrySwap      LedgerEntryKind = "swap"
	LedgerEntryGas       LedgerEntryKind = "gas"
	LedgerEntrySlippage  LedgerEntryKind = "slippage"
	LedgerEntryRug       LedgerEntryKind = "rug"
)

// LedgerEntry represents a single PnL line item in the append-only ledger.
// Each entry records one component of a position's profit/loss at a specific
// block, enabling accurate aggregation and forensic analysis.
//
// Ledger entries are immutable once written; corrections are made by
// inserting a new entry with adjusted values, never by UPDATE.
type LedgerEntry struct {
	ID          string
	PositionID  string
	Kind        LedgerEntryKind
	Amount      domain.Decimal // net amount; negative = loss, positive = gain
	TokenSymbol string         // symbol of token (e.g., "ETH", "USDC")
	BlockRef    domain.BlockRef
	TxHash      string // optional: nil if estimated/marked without tx
}

// LedgerRepo defines the persistence interface for the append-only PnL ledger.
// Implementations handle both SQLite and Postgres backends via sqlc.
//
// All methods are idempotent where possible; concurrent writes are handled
// via INSERT OR IGNORE / ON CONFLICT DO NOTHING.
type LedgerRepo interface {
	// Append adds a new ledger entry to the append-only ledger.
	// It returns the inserted entry with its assigned ID.
	//
	// Duplicate detection is not enforced at this layer; callers should
	// ensure idempotency via event_id or external deduplication.
	//
	// Returns an error if the underlying DB write fails.
	Append(ctx context.Context, entry LedgerEntry) (LedgerEntry, error)

	// ByPosition returns all ledger entries for a given position, ordered by time.
	// Returns an empty slice (not nil) if no entries exist.
	//
	// The returned entries are ordered by block number ascending.
	ByPosition(ctx context.Context, positionID string) ([]LedgerEntry, error)

	// ByPositionAndKind returns ledger entries filtered by position and kind.
	// Useful for aggregating fee-only or IL-only totals.
	ByPositionAndKind(ctx context.Context, positionID string, kind LedgerEntryKind) ([]LedgerEntry, error)

	// AggregateByKind computes the total net PnL for a position by entry kind.
	// Returns a map from LedgerEntryKind to sum, including zero entries for
	// kinds with no entries.
	//
	// Note: This is a read-only aggregation; it does not create new entries.
	AggregateByKind(ctx context.Context, positionID string) (map[LedgerEntryKind]domain.Decimal, error)

	// LatestBlock returns the highest block number with any ledger entry,
	// or nil if no entries exist. Used for pagination and checkpointing.
	LatestBlock(ctx context.Context) (*domain.BlockRef, error)
}