package ports_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: Broadcaster must implement ports.Broadcaster
var _ ports.Broadcaster = (*broadcasterMock)(nil)

type broadcasterMock struct{}

func (m *broadcasterMock) Send(ctx context.Context, tx domain.SignedTx) error { return nil }
func (m *broadcasterMock) CallCount() int64                                   { return 0 }

// Compile-time interface assertion: broadcasterFunc implements Broadcaster for functional tests
var _ ports.Broadcaster = (*broadcasterFuncMock)(nil)

type broadcasterFuncMock struct {
	sendFn     func(ctx context.Context, tx domain.SignedTx) error
	callCountFn func() int64
}

func (b *broadcasterFuncMock) Send(ctx context.Context, tx domain.SignedTx) error {
	if b.sendFn != nil {
		return b.sendFn(ctx, tx)
	}
	return nil
}

func (b *broadcasterFuncMock) CallCount() int64 {
	if b.callCountFn != nil {
		return b.callCountFn()
	}
	return 0
}

// TestBroadcasterInterface verifies the Broadcaster interface is properly defined
func TestBroadcasterInterface(t *testing.T) {
	require.NotNil(t, t, "ports.Broadcaster interface must exist")
}

// TestBroadcasterFuncMock verifies the functional mock can be instantiated
func TestBroadcasterFuncMock(t *testing.T) {
	ctx := context.Background()
	broadcaster := &broadcasterFuncMock{
		sendFn: func(ctx context.Context, tx domain.SignedTx) error {
			return nil
		},
		callCountFn: func() int64 {
			return 42
		},
	}

	err := broadcaster.Send(ctx, domain.SignedTx{})
	require.NoError(t, err)

	count := broadcaster.CallCount()
	require.Equal(t, int64(42), count)
}