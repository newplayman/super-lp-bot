// Package timex provides utilities for working with block timestamps.
// Key invariant: wall-clock time must NOT enter business logic paths.
// All business logic uses block timestamps extracted from context.
package timex

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// contextKey is a custom type for context keys to avoid collisions.
type contextKey string

const blockRefKey contextKey = "lpbot:platform:timex:blockref"

// BlockRef returns the BlockRef stored in the context, or a zero value if none.
// Use this to access the full block reference including chain, number, hash, and timestamp.
func BlockRef(ctx context.Context) domain.BlockRef {
	if ref, ok := ctx.Value(blockRefKey).(domain.BlockRef); ok {
		return ref
	}
	return domain.BlockRef{}
}

// BlockTime returns the block timestamp (Unix seconds) from the context.
// Returns 0 if no BlockRef is present in the context.
// This is the primary function for business logic to obtain the current block time.
func BlockTime(ctx context.Context) int64 {
	return BlockRef(ctx).TimeUnix
}

// WithBlockRef returns a new context with the given BlockRef attached.
// The BlockRef carries business time (chain, block_number, block_hash, block_time_unix).
// Use this when entering a block-scoped operation (e.g., processing a new block).
func WithBlockRef(ctx context.Context, ref domain.BlockRef) context.Context {
	return context.WithValue(ctx, blockRefKey, ref)
}
