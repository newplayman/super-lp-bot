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

	// Create tables
	schema := `
	CREATE TABLE dryrun_pools (
		pool_id TEXT PRIMARY KEY,
		chain INTEGER NOT NULL,
		protocol TEXT NOT NULL,
		token0 TEXT NOT NULL,
		token1 TEXT NOT NULL,
		fee_bps INTEGER NOT NULL,
		tier TEXT,
		audit_verdict TEXT,
		last_score TEXT,
		updated_block INTEGER NOT NULL,
		updated_at INTEGER NOT NULL
	);

	CREATE TABLE dryrun_pool_score_history (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		pool_id TEXT NOT NULL,
		chain INTEGER NOT NULL,
		block_number INTEGER NOT NULL,
		block_hash TEXT NOT NULL,
		block_time INTEGER NOT NULL,
		score_json TEXT NOT NULL,
		trace_id TEXT NOT NULL
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
	repo := NewPoolRepo(db)

	poolWithScore := ports.PoolWithScore{
		Pool: domain.Pool{
			ID:        "0x123",
			Chain:     domain.ChainBase,
			Protocol:  "uniswap_v3",
			Token0:    domain.MustParseAddress("0x0000000000000000000000000000000000000001"),
			Token1:    domain.MustParseAddress("0x0000000000000000000000000000000000000002"),
			FeeBPS:    30,
			Tier_:     domain.TierA,
			Liquidity: domain.MustDecimal("1000000"),
			Tick:      0,
			TVLUSD:    domain.MustDecimal("500000"),
			Vol24h:    domain.MustDecimal("100000"),
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

	// Verify score history was created
	history, err := repo.GetScoreHistory(context.Background(), "base:uniswap_v3:0x123", 10)
	require.NoError(t, err)
	assert.Len(t, history, 1)
	assert.Equal(t, "base:uniswap_v3:0x123", history[0].PoolKey)
}

func TestPoolRepo_GetPool(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db)

	// Insert a pool directly
	_, err := db.ExecContext(context.Background(), `
		INSERT INTO dryrun_pools (pool_id, chain, protocol, token0, token1, fee_bps, updated_block, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`, "0xabc", 0, "uniswap_v3", "0x0000000000000000000000000000000000000001",
		"0x0000000000000000000000000000000000000002", 30, 0, 1700000000)
	require.NoError(t, err)

	// Test GetPool
	pool, err := repo.GetPool(context.Background(), "base:uniswap_v3:0xabc")
	require.NoError(t, err)
	assert.Equal(t, "0xabc", pool.ID)
	assert.Equal(t, domain.ChainBase, pool.Chain)
	assert.Equal(t, "uniswap_v3", pool.Protocol)

	// Test non-existent pool
	_, err = repo.GetPool(context.Background(), "base:uniswap_v3:0xnonexistent")
	assert.ErrorIs(t, err, ports.ErrPoolNotFound)
}

func TestPoolRepo_ListPools(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db)

	// Insert multiple pools
	pools := []struct {
		poolID   string
		chain    int
		protocol string
		tier     string
		updatedAt int64
	}{
		{"pool1", 0, "uniswap_v3", "A", 1700000001},
		{"pool2", 0, "uniswap_v3", "B", 1700000002},
		{"pool3", 1, "whirlpool", "A", 1700000003},
	}

	for _, p := range pools {
		_, err := db.ExecContext(context.Background(), `
			INSERT INTO dryrun_pools (pool_id, chain, protocol, token0, token1, fee_bps, tier, updated_block, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		`, p.poolID, p.chain, p.protocol,
			"0x0000000000000000000000000000000000000001",
			"0x0000000000000000000000000000000000000002",
			30, p.tier, 0, p.updatedAt)
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
	repo := NewPoolRepo(db)

	// Insert score history
	scores := []string{
		`{"FeeAPRScore":70,"TvlScore":60,"VolScore":50,"VolatilityScore":80,"SecurityScore":90,"Total":70}`,
		`{"FeeAPRScore":80,"TvlScore":70,"VolScore":60,"VolatilityScore":75,"SecurityScore":95,"Total":77.5}`,
		`{"FeeAPRScore":85,"TvlScore":75,"VolScore":65,"VolatilityScore":70,"SecurityScore":90,"Total":79}`,
	}

	for i, score := range scores {
		_, err := db.ExecContext(context.Background(), `
			INSERT INTO dryrun_pool_score_history (pool_id, chain, block_number, block_hash, block_time, score_json, trace_id)
			VALUES (?, ?, ?, ?, ?, ?, ?)
		`, "0xpool", 0, i, "hash", 1700000000+int64(i), score, "trace")
		require.NoError(t, err)
	}

	// Test GetScoreHistory
	history, err := repo.GetScoreHistory(context.Background(), "base:uniswap_v3:0xpool", 10)
	require.NoError(t, err)
	assert.Len(t, history, 3)

	// Verify ordering (ASC by timestamp)
	assert.Equal(t, int64(1700000000), history[0].Timestamp)
	assert.Equal(t, int64(1700000001), history[1].Timestamp)
	assert.Equal(t, int64(1700000002), history[2].Timestamp)

	// Test with limit
	limited, err := repo.GetScoreHistory(context.Background(), "base:uniswap_v3:0xpool", 2)
	require.NoError(t, err)
	assert.Len(t, limited, 2)

	// Test non-existent pool
	empty, err := repo.GetScoreHistory(context.Background(), "base:uniswap_v3:nonexistent", 10)
	require.NoError(t, err)
	assert.Empty(t, empty)
}

func TestPoolRepo_UpsertAuditVerdict(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db)

	// Insert a pool
	_, err := db.ExecContext(context.Background(), `
		INSERT INTO dryrun_pools (pool_id, chain, protocol, token0, token1, fee_bps, updated_block, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`, "0xtest", 0, "uniswap_v3", "0x0000000000000000000000000000000000000001",
		"0x0000000000000000000000000000000000000002", 30, 0, 1700000000)
	require.NoError(t, err)

	// Test UpsertAuditVerdict
	err = repo.UpsertAuditVerdict(context.Background(), "base:uniswap_v3:0xtest", domain.AuditPass, 10.0)
	require.NoError(t, err)

	// Verify the verdict was set
	pool, err := repo.GetPool(context.Background(), "base:uniswap_v3:0xtest")
	require.NoError(t, err)
	assert.NotEmpty(t, pool.ID)

	// Check verdict in database
	var verdict string
	err = db.QueryRowContext(context.Background(), "SELECT audit_verdict FROM dryrun_pools WHERE pool_id = ?", "0xtest").Scan(&verdict)
	require.NoError(t, err)
	assert.Equal(t, "pass", verdict)

	// Test updating to warn
	err = repo.UpsertAuditVerdict(context.Background(), "base:uniswap_v3:0xtest", domain.AuditWarn, 50.0)
	require.NoError(t, err)

	// Verify update
	err = db.QueryRowContext(context.Background(), "SELECT audit_verdict FROM dryrun_pools WHERE pool_id = ?", "0xtest").Scan(&verdict)
	require.NoError(t, err)
	assert.Equal(t, "warn", verdict)

	// Test non-existent pool
	err = repo.UpsertAuditVerdict(context.Background(), "base:uniswap_v3:nonexistent", domain.AuditFail, 100.0)
	assert.ErrorIs(t, err, ports.ErrPoolNotFound)
}

func TestPoolRepo_InvalidKeyFormat(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()
	repo := NewPoolRepo(db)

	// Test GetPool with invalid key
	_, err := repo.GetPool(context.Background(), "invalid-key")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid pool key format")

	// Test GetScoreHistory with invalid key
	_, err = repo.GetScoreHistory(context.Background(), "invalid-key", 10)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid pool key format")

	// Test UpsertAuditVerdict with invalid key
	err = repo.UpsertAuditVerdict(context.Background(), "invalid-key", domain.AuditPass, 0)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid pool key format")
}

func TestMain(m *testing.M) {
	os.Exit(m.Run())
}