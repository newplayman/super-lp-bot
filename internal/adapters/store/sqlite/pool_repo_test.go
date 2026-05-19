package sqlite

import (
	"context"
	"database/sql"
	"os"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	_ "github.com/mattn/go-sqlite3"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func setupTestDB(t *testing.T) *sql.DB {
	db, err := sql.Open("sqlite3", ":memory:")
	require.NoError(t, err)

	// Create tables with prefix
	schema := `
	CREATE TABLE test_pools (
		id TEXT PRIMARY KEY,
		chain TEXT NOT NULL,
		protocol TEXT NOT NULL,
		token0 TEXT NOT NULL,
		token1 TEXT NOT NULL,
		fee_bps INTEGER NOT NULL,
		tier TEXT,
		tvl_usd TEXT,
		vol_24h TEXT,
		fee_apr_24h TEXT,
		last_score TEXT,
		updated_at INTEGER NOT NULL
	);
	`
	_, err = db.Exec(schema)
	require.NoError(t, err)

	return db
}

// Compile-time interface assertion
var _ ports.PoolRepo = (*PoolRepo)(nil)

func TestPoolRepo_UpsertPool(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db, "test_")

	poolWithScore := ports.PoolWithScore{
		Pool: domain.Pool{
			ID:       "0x123",
			Chain:    domain.ChainBase,
			Protocol: "uniswap_v3",
			Token0:   domain.MustParseAddress("0x0000000000000000000000000000000000000001"),
			Token1:   domain.MustParseAddress("0x0000000000000000000000000000000000000002"),
			FeeBPS:   30,
			Tier_:    domain.TierA,
			TVLUSD:   domain.MustDecimal("500000"),
			Vol24h:   domain.MustDecimal("100000"),
			FeeAPR24h: domain.MustDecimal("0.05"),
			UpdatedAt: 1700000000,
		},
		Score: domain.Score{
			FeeAPRScore:     85,
			TvlScore:        70,
			VolScore:        60,
			VolatilityScore: 75,
			SecurityScore:   90,
			Total:           77.5,
		},
	}

	err := repo.UpsertPool(context.Background(), poolWithScore)
	require.NoError(t, err)

	// Verify the pool was inserted
	pool, err := repo.GetPool(context.Background(), "base:uniswap_v3:0x123")
	require.NoError(t, err)
	assert.Equal(t, "0x123", pool.ID)
	assert.Equal(t, domain.ChainBase, pool.Chain)
	assert.Equal(t, "uniswap_v3", pool.Protocol)
	assert.Equal(t, uint(30), pool.FeeBPS)
	assert.Equal(t, domain.TierA, pool.Tier_)
}

func TestPoolRepo_GetPool(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db, "test_")

	// Insert a pool directly
	_, err := db.ExecContext(context.Background(), `
		INSERT INTO test_pools (id, chain, protocol, token0, token1, fee_bps, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`, "0xabc", "base", "uniswap_v3", "0x0000000000000000000000000000000000000001",
		"0x0000000000000000000000000000000000000002", 30, 1700000000)
	require.NoError(t, err)

	// Test GetPool
	pool, err := repo.GetPool(context.Background(), "base:uniswap_v3:0xabc")
	require.NoError(t, err)
	assert.Equal(t, "0xabc", pool.ID)
	assert.Equal(t, domain.ChainBase, pool.Chain)
	assert.Equal(t, "uniswap_v3", pool.Protocol)

	// Test non-existent pool
	_, err = repo.GetPool(context.Background(), "base:uniswap_v3:0xnonexistent")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "no rows")
}

func TestPoolRepo_ListPools(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db, "test_")

	// Insert multiple pools
	pools := []struct {
		poolID     string
		chain      string
		protocol   string
		tier       string
		updatedAt  int64
	}{
		{"pool1", "base", "uniswap_v3", "A", 1700000001},
		{"pool2", "base", "uniswap_v3", "B", 1700000002},
		{"pool3", "solana", "whirlpool", "A", 1700000003},
	}

	for _, p := range pools {
		_, err := db.ExecContext(context.Background(), `
			INSERT INTO test_pools (id, chain, protocol, token0, token1, fee_bps, tier, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		`, p.poolID, p.chain, p.protocol,
			"0x0000000000000000000000000000000000000001",
			"0x0000000000000000000000000000000000000002",
			30, p.tier, p.updatedAt)
		require.NoError(t, err)
	}

	// Test ListPools - no filter
	all, err := repo.ListPools(context.Background(), ports.PoolFilter{})
	require.NoError(t, err)
	assert.Len(t, all, 3)

	// Test ListPools - filter by chain
	baseOnly, err := repo.ListPools(context.Background(), ports.PoolFilter{Chain: domain.ChainBase})
	require.NoError(t, err)
	assert.Len(t, baseOnly, 2)

	// Test ListPools - filter by tier
	tierA, err := repo.ListPools(context.Background(), ports.PoolFilter{Tier: domain.TierA})
	require.NoError(t, err)
	assert.Len(t, tierA, 2)

	// Test ListPools - combined filter
	solanaA, err := repo.ListPools(context.Background(), ports.PoolFilter{
		Chain: domain.ChainSolana,
		Tier:  domain.TierA,
	})
	require.NoError(t, err)
	assert.Len(t, solanaA, 1)
	assert.Equal(t, "pool3", solanaA[0].ID)

	// Test ListPools - with limit
	limited, err := repo.ListPools(context.Background(), ports.PoolFilter{Limit: 2})
	require.NoError(t, err)
	assert.Len(t, limited, 2)
}

func TestPoolRepo_GetScoreHistory(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db, "test_")

	// Test with non-existent pool returns empty
	history, err := repo.GetScoreHistory(context.Background(), "base:uniswap_v3:nonexistent", 10)
	require.NoError(t, err)
	assert.Empty(t, history)
}

func TestPoolRepo_UpsertAuditVerdict(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db, "test_")

	// Insert a pool
	_, err := db.ExecContext(context.Background(), `
		INSERT INTO test_pools (id, chain, protocol, token0, token1, fee_bps, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`, "0xtest", "base", "uniswap_v3", "0x0000000000000000000000000000000000000001",
		"0x0000000000000000000000000000000000000002", 30, 1700000000)
	require.NoError(t, err)

	// Test UpsertAuditVerdict (simplified implementation)
	err = repo.UpsertAuditVerdict(context.Background(), "base:uniswap_v3:0xtest", domain.AuditPass, 10.0)
	require.NoError(t, err)
}

func TestPoolRepo_InvalidKeyFormat(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db, "test_")

	// Test GetPool with invalid key
	_, err := repo.GetPool(context.Background(), "invalid-key")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid pool key format")
}

func TestMain(m *testing.M) {
	os.Exit(m.Run())
}