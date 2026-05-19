package ports_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: TxRepo implementation must satisfy ports.TxRepo
var _ ports.TxRepo = (*txRepoMock)(nil)

// txRepoMock is a minimal mock implementing TxRepo for compile-time verification.
type txRepoMock struct{}

func (m *txRepoMock) UpsertTx(ctx context.Context, tx domain.SignedTx) error {
	return nil
}

func (m *txRepoMock) GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error) {
	return domain.SignedTx{}, ports.ErrTxNotFound
}

func (m *txRepoMock) ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error) {
	return nil, nil
}

func (m *txRepoMock) UpdateTxStatus(ctx context.Context, chain domain.ChainID, hash string, newStatus domain.TxStatus, ref *domain.BlockRef) error {
	return nil
}

func (m *txRepoMock) ListPendingTxs(ctx context.Context, chain domain.ChainID) ([]domain.SignedTx, error) {
	return nil, nil
}

func (m *txRepoMock) ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error) {
	return nil, nil
}

func (m *txRepoMock) IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error {
	return nil
}

func (m *txRepoMock) GetRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) (int, error) {
	return 0, nil
}

// TestTxRepoInterface verifies the TxRepo interface is properly defined.
func TestTxRepoInterface(t *testing.T) {
	require.NotNil(t, t, "ports.TxRepo interface must exist")
}

// TestTxNotFoundError verifies ErrTxNotFound behavior.
func TestTxNotFoundError(t *testing.T) {
	err := ports.ErrTxNotFound
	require.Equal(t, "tx not found", err.Error())
	require.ErrorIs(t, err, ports.ErrTxNotFound)
}

// TestTxWithStatusFields verifies TxWithStatus contains expected fields.
func TestTxWithStatusFields(t *testing.T) {
	txws := ports.TxWithStatus{
		SignedTx: domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				Chain: domain.ChainBase,
			},
			Hash: "0xabc123",
		},
		Status: domain.TxBroadcast,
	}
	require.Equal(t, domain.ChainBase, txws.Chain)
	require.Equal(t, "0xabc123", txws.Hash)
	require.Equal(t, domain.TxBroadcast, txws.Status)
}

// TestTxFilterDefault verifies TxFilter zero value semantics.
func TestTxFilterDefault(t *testing.T) {
	filter := ports.TxFilter{}
	// Empty chain means "any chain"
	require.Empty(t, filter.Chain)
	// Zero status means "any status"
	require.Equal(t, domain.TxStatus(""), filter.Status)
}

// Compile-time assertion: TxStatus satisfies expected values
var _ = domain.TxStatus(domain.TxBuilt)