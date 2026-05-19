//go:build !live

// Package none implements a no-op wallet adapter for lp-bot.
//
// This adapter is only compiled in non-live builds (dryrun/shadow mode).
// All signing operations panic to enforce the invariant that wallet signing
// must not occur in non-live builds.
//
// Invariant violations logged:
//   - Sign: panic("invariant violation: wallet.Sign invoked in non-live build")
//   - ApproveExact: panic("invariant violation: wallet.ApproveExact invoked in non-live build")
//   - Revoke: panic("invariant violation: wallet.Revoke invoked in non-live build")
//
// See spec §6.8 (invariant #9/#10) and spec §6.7 (invariant #3).
package none

import (
	"context"
	"math/big"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// wallet implements a no-op wallet that panics on all signing operations.
type wallet struct{}

// New creates a new none wallet instance.
//
// No configuration is required; this wallet always panics on signing operations.
func New(ctx context.Context) (ports.Wallet, error) {
	return &wallet{}, nil
}

// Open is a no-op for the none wallet.
func (w *wallet) Open(ctx context.Context) error {
	return nil
}

// Close is a no-op for the none wallet.
func (w *wallet) Close() error {
	return nil
}

// Address returns an empty address for the none wallet.
func (w *wallet) Address() domain.Address {
	return domain.Address{}
}

// Chain returns an empty chain ID for the none wallet.
func (w *wallet) Chain() domain.ChainID {
	return ""
}

// Sign panics to enforce invariant violation.
//
// Invariant #3: dryrun mode must not broadcast any transactions.
// Invariant #9: signing must only occur in live mode.
func (w *wallet) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	panic("invariant violation: wallet.Sign invoked in non-live build")
}

// ApproveExact panics to enforce invariant violation.
//
// Invariant #3: dryrun mode must not broadcast any transactions.
// Invariant #9: ApproveExact must only occur in live mode.
func (w *wallet) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	panic("invariant violation: wallet.ApproveExact invoked in non-live build")
}

// Revoke panics to enforce invariant violation.
//
// Invariant #3: dryrun mode must not broadcast any transactions.
// Invariant #10: Revoke must only occur in live mode.
func (w *wallet) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	panic("invariant violation: wallet.Revoke invoked in non-live build")
}