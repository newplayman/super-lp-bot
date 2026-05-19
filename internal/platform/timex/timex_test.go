package timex_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/timex"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestBlockTime(t *testing.T) {
	t.Run("returns zero when context has no BlockRef", func(t *testing.T) {
		ctx := context.Background()
		ts := timex.BlockTime(ctx)
		assert.Equal(t, int64(0), ts)
	})

	t.Run("returns TimeUnix from BlockRef in context", func(t *testing.T) {
		ref := domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   12345678,
			Hash:     "0xabc123",
			TimeUnix: 1718000000,
		}
		ctx := timex.WithBlockRef(context.Background(), ref)
		ts := timex.BlockTime(ctx)
		assert.Equal(t, int64(1718000000), ts)
	})

	t.Run("uses nearest ancestor BlockRef", func(t *testing.T) {
		// Parent context has BlockRef
		parentRef := domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   10000000,
			Hash:     "0xparent",
			TimeUnix: 1700000000,
		}
		parentCtx := timex.WithBlockRef(context.Background(), parentRef)

		// Child context without BlockRef should inherit from parent
		childCtx := context.WithValue(parentCtx, "other_key", "other_value")
		ts := timex.BlockTime(childCtx)
		assert.Equal(t, int64(1700000000), ts)
	})

	t.Run("child BlockRef shadows parent BlockRef", func(t *testing.T) {
		// Parent context has BlockRef
		parentRef := domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   10000000,
			Hash:     "0xparent",
			TimeUnix: 1700000000,
		}
		parentCtx := timex.WithBlockRef(context.Background(), parentRef)

		// Child context overrides with new BlockRef
		childRef := domain.BlockRef{
			Chain:    domain.ChainSolana,
			Number:   20000000,
			Hash:     "0xchild",
			TimeUnix: 1710000000,
		}
		childCtx := timex.WithBlockRef(parentCtx, childRef)

		// Child's BlockRef should be used
		ts := timex.BlockTime(childCtx)
		assert.Equal(t, int64(1710000000), ts)
	})
}

func TestWithBlockRef(t *testing.T) {
	t.Run("stores BlockRef in context", func(t *testing.T) {
		ref := domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   5000000,
			Hash:     "0xdef456",
			TimeUnix: 1699999999,
		}
		ctx := timex.WithBlockRef(context.Background(), ref)
		require.NotNil(t, ctx)

		// Verify BlockTime returns the stored value
		ts := timex.BlockTime(ctx)
		assert.Equal(t, int64(1699999999), ts)
	})

	t.Run("preserves existing context values", func(t *testing.T) {
		parentCtx := context.WithValue(context.Background(), "mykey", "myvalue")
		ref := domain.BlockRef{
			Chain:    domain.ChainSolana,
			Number:   100,
			Hash:     "0xsol",
			TimeUnix: 1600000000,
		}
		ctx := timex.WithBlockRef(parentCtx, ref)

		// Original value should still be accessible
		val := ctx.Value("mykey")
		assert.Equal(t, "myvalue", val)

		// BlockRef should also be accessible
		ts := timex.BlockTime(ctx)
		assert.Equal(t, int64(1600000000), ts)
	})
}
