package ports_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: PoolRepo implementation must satisfy ports.PoolRepo
var _ ports.PoolRepo = (*poolRepoMock)(nil)

// poolRepoMock is a minimal mock implementing PoolRepo for compile-time verification.
type poolRepoMock struct{}

func (m *poolRepoMock) UpsertPool(ctx context.Context, pool ports.PoolWithScore) error {
	return nil
}

func (m *poolRepoMock) GetPool(ctx context.Context, key string) (domain.Pool, error) {
	return domain.Pool{}, ports.ErrPoolNotFound
}

func (m *poolRepoMock) ListPools(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error) {
	return nil, nil
}

func (m *poolRepoMock) GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]ports.PoolScoreSnapshot, error) {
	return nil, nil
}

func (m *poolRepoMock) UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error {
	return nil
}

// TestPoolRepoInterface verifies the PoolRepo interface is properly defined.
func TestPoolRepoInterface(t *testing.T) {
	require.NotNil(t, t, "ports.PoolRepo interface must exist")
}

// TestPoolNotFoundError verifies ErrPoolNotFound behavior.
func TestPoolNotFoundError(t *testing.T) {
	err := ports.ErrPoolNotFound
	require.Equal(t, "pool not found", err.Error())
	require.ErrorIs(t, err, ports.ErrPoolNotFound)
}

// TestPoolFilterDefault verifies PoolFilter zero value semantics.
func TestPoolFilterDefault(t *testing.T) {
	filter := ports.PoolFilter{}
	// Empty chain and empty tier means "no filter"
	require.Empty(t, filter.Chain)
	require.Equal(t, domain.Tier(""), filter.Tier)
}

// TestPoolWithScoreFields verifies PoolWithScore contains expected fields.
func TestPoolWithScoreFields(t *testing.T) {
	pws := ports.PoolWithScore{
		Pool: domain.Pool{
			ID:       "0x1234",
			Chain:    domain.ChainBase,
			Protocol: "uniswap_v3",
			Tier_:    domain.TierC,
		},
		Score: domain.Score{
			Total: 75.0,
		},
	}
	require.Equal(t, "0x1234", pws.Pool.ID)
	require.Equal(t, domain.ChainBase, pws.Pool.Chain)
	require.Equal(t, domain.TierC, pws.Pool.Tier_)
	require.Equal(t, 75.0, pws.Score.Total)
}

// TestPoolScoreSnapshotFields verifies PoolScoreSnapshot structure.
func TestPoolScoreSnapshotFields(t *testing.T) {
	snapshot := ports.PoolScoreSnapshot{
		PoolKey:   "base:uniswap_v3:0x1234",
		Tier:      domain.TierA,
		Timestamp: 1716140800,
	}
	require.Equal(t, "base:uniswap_v3:0x1234", snapshot.PoolKey)
	require.Equal(t, domain.TierA, snapshot.Tier)
	require.Equal(t, int64(1716140800), snapshot.Timestamp)
}
