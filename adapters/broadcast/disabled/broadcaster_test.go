//go:build !live

package disabled

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

// TestBroadcasterSendPanics verifies that Send panics when called.
func TestBroadcasterSendPanics(t *testing.T) {
	b := &Broadcaster{}

	var panicked bool
	var panicValue interface{}

	// Recover from the panic
	defer func() {
		panicValue = recover()
		panicked = panicValue != nil
	}()

	// This should panic
	err := b.Send(nil, txFromTest())
	_ = err // unreachable

	require.True(t, panicked, "Send should panic in disabled adapter")
	require.Equal(t, "invariant #3 violation: broadcaster.Send invoked in non-live build", panicValue)
}

// TestBroadcasterIncrementsCounter verifies that Send increments both
// the prometheus metric and the internal counter.
func TestBroadcasterIncrementsCounter(t *testing.T) {
	b := &Broadcaster{}

	// Get initial call count
	initialCount := b.CallCount()
	require.Equal(t, int64(0), initialCount)

	// Attempt call and recover from panic
	defer func() {
		recover()
	}()

	_ = b.Send(nil, txFromTest())

	// Counter should be incremented
	require.Equal(t, int64(1), b.CallCount())
}

// TestBroadcasterMultipleSends verifies counter increments correctly
// across multiple calls.
func TestBroadcasterMultipleSends(t *testing.T) {
	b := &Broadcaster{}

	// Attempt multiple calls and recover from panic each time
	defer func() {
		recover()
	}()

	for i := 0; i < 5; i++ {
		_ = b.Send(nil, txFromTest())
	}

	require.Equal(t, int64(5), b.CallCount())
}

// txFromTest creates a minimal SignedTx for testing.
func txFromTest() domain.SignedTx {
	return domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			Chain: domain.ChainID("test"),
		},
		Hash: "0xtest",
	}
}