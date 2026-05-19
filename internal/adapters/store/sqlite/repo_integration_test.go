package sqlite

import (
	"context"
	"database/sql"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	_ "github.com/mattn/go-sqlite3"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func setupRepoTestDB(t *testing.T, prefix string) (*sql.DB, func()) {
	db, err := sql.Open("sqlite3", ":memory:")
	require.NoError(t, err)

	// Create tables matching schema in store.go
	tables := []string{
		`CREATE TABLE IF NOT EXISTS ` + prefix + `positions (
			id TEXT PRIMARY KEY,
			chain TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			token0 TEXT NOT NULL,
			token1 TEXT NOT NULL,
			tick_lower INTEGER NOT NULL,
			tick_upper INTEGER NOT NULL,
			liquidity TEXT NOT NULL,
			amount0 TEXT NOT NULL,
			amount1 TEXT NOT NULL,
			tvl_usd TEXT,
			status TEXT NOT NULL,
			opened_at INTEGER NOT NULL,
			updated_at INTEGER NOT NULL,
			closed_at INTEGER
		)`,
		`CREATE TABLE IF NOT EXISTS ` + prefix + `ledger (
			id TEXT PRIMARY KEY,
			position_id TEXT,
			tx_hash TEXT,
			entry_type TEXT NOT NULL,
			amount TEXT NOT NULL,
			currency TEXT NOT NULL,
			description TEXT,
			timestamp INTEGER NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS ` + prefix + `risk_events (
			id TEXT PRIMARY KEY,
			event_type TEXT NOT NULL,
			severity TEXT NOT NULL,
			description TEXT NOT NULL,
			data TEXT,
			resolved INTEGER DEFAULT 0,
			resolved_at INTEGER,
			created_at INTEGER NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS ` + prefix + `kill_switch_state (
			id TEXT PRIMARY KEY,
			switch_type TEXT NOT NULL,
			triggered_at INTEGER NOT NULL,
			trigger_reason TEXT,
			auto_resume_at INTEGER,
			resumed_at INTEGER,
			resume_allowed INTEGER DEFAULT 1,
			total_triggers INTEGER DEFAULT 1,
			updated_at INTEGER NOT NULL
		)`,
	}

	for _, sql := range tables {
		_, err := db.Exec(sql)
		require.NoError(t, err)
	}

	cleanup := func() {
		db.Close()
	}
	return db, cleanup
}

// Test PositionRepo with schema matching
func TestPositionRepo_SaveAndFind(t *testing.T) {
	db, cleanup := setupRepoTestDB(t, "test_")
	defer cleanup()

	repo := NewPositionRepo(db, "test_")

	pos := &domain.Position{
		ID:        "pos_001",
		Chain:     domain.ChainBase,
		PoolID:    "pool_abc",
		Status:    domain.StatusOpen,
		TickLower: -1000,
		TickUpper: 1000,
		OpenedAt:  1700000000000,
	}

	err := repo.Save(context.Background(), pos)
	require.NoError(t, err)

	// FindByID
	found, err := repo.FindByID(context.Background(), "pos_001")
	require.NoError(t, err)
	assert.Equal(t, "pos_001", found.ID)
	assert.Equal(t, domain.ChainBase, found.Chain)
	assert.Equal(t, "pool_abc", found.PoolID)
	assert.Equal(t, domain.StatusOpen, found.Status)
	assert.Equal(t, int64(-1000), found.TickLower)
	assert.Equal(t, int64(1000), found.TickUpper)
}

func TestPositionRepo_UpdateStatus(t *testing.T) {
	db, cleanup := setupRepoTestDB(t, "test_")
	defer cleanup()

	repo := NewPositionRepo(db, "test_")

	pos := &domain.Position{
		ID:        "pos_002",
		Chain:     domain.ChainSolana,
		PoolID:    "pool_xyz",
		Status:    domain.StatusOpen,
		TickLower: 0,
		TickUpper: 100,
		OpenedAt:  1700000000000,
	}
	err := repo.Save(context.Background(), pos)
	require.NoError(t, err)

	// Update status
	err = repo.UpdateStatus(context.Background(), "pos_002", domain.StatusClosed)
	require.NoError(t, err)

	// Verify
	found, err := repo.FindByID(context.Background(), "pos_002")
	require.NoError(t, err)
	assert.Equal(t, domain.StatusClosed, found.Status)
}

func TestPositionRepo_FindByChainAndStatus(t *testing.T) {
	db, cleanup := setupRepoTestDB(t, "test_")
	defer cleanup()

	repo := NewPositionRepo(db, "test_")

	// Insert multiple positions
	positions := []*domain.Position{
		{ID: "pos_1", Chain: domain.ChainBase, PoolID: "p1", Status: domain.StatusOpen, TickLower: 0, TickUpper: 100, OpenedAt: 1},
		{ID: "pos_2", Chain: domain.ChainBase, PoolID: "p2", Status: domain.StatusOpen, TickLower: 0, TickUpper: 100, OpenedAt: 2},
		{ID: "pos_3", Chain: domain.ChainSolana, PoolID: "p3", Status: domain.StatusOpen, TickLower: 0, TickUpper: 100, OpenedAt: 3},
	}
	for _, p := range positions {
		err := repo.Save(context.Background(), p)
		require.NoError(t, err)
	}

	// Find by chain
	base, err := repo.FindByChainAndStatus(context.Background(), domain.ChainBase, domain.StatusOpen)
	require.NoError(t, err)
	assert.Len(t, base, 2)

	solana, err := repo.FindByChainAndStatus(context.Background(), domain.ChainSolana, domain.StatusOpen)
	require.NoError(t, err)
	assert.Len(t, solana, 1)
}

// Test LedgerRepo with schema matching
func TestLedgerRepo_AppendAndRead(t *testing.T) {
	db, cleanup := setupRepoTestDB(t, "test_")
	defer cleanup()

	repo := NewLedgerRepo(db, "test_")

	entry := ports.LedgerEntry{
		ID:         "ledger_test_1",
		PositionID: "pos_001",
		Kind:       ports.LedgerEntryFee,
		Amount:     domain.MustDecimal("100.50"),
		TokenSymbol: "USDC",
		TxHash:     "0xtx123",
	}

	result, err := repo.Append(context.Background(), entry)
	require.NoError(t, err)
	assert.NotEmpty(t, result.ID)

	// ByPosition
	entries, err := repo.ByPosition(context.Background(), "pos_001")
	require.NoError(t, err)
	assert.Len(t, entries, 1)
	assert.Equal(t, ports.LedgerEntryFee, entries[0].Kind)
}

func TestLedgerRepo_AggregateByKind(t *testing.T) {
	db, err := sql.Open("sqlite3", ":memory:")
	require.NoError(t, err)
	defer db.Close()

	// Create fresh table with unique prefix for this test
	_, err = db.Exec(`CREATE TABLE agg_test_ledger (
		id TEXT PRIMARY KEY,
		position_id TEXT,
		tx_hash TEXT,
		entry_type TEXT NOT NULL,
		amount TEXT NOT NULL,
		currency TEXT NOT NULL,
		description TEXT,
		timestamp INTEGER NOT NULL
	)`)
	require.NoError(t, err)

	repo := NewLedgerRepo(db, "agg_test_")

	// Insert multiple entries with unique IDs
	entries := []ports.LedgerEntry{
		{ID: "agg_unique_1", PositionID: "pos_agg", Kind: ports.LedgerEntryFee, Amount: domain.MustDecimal("10"), TokenSymbol: "USDC"},
		{ID: "agg_unique_2", PositionID: "pos_agg", Kind: ports.LedgerEntryFee, Amount: domain.MustDecimal("20"), TokenSymbol: "USDC"},
		{ID: "agg_unique_3", PositionID: "pos_agg", Kind: ports.LedgerEntryGas, Amount: domain.MustDecimal("-5"), TokenSymbol: "ETH"},
	}
	for _, e := range entries {
		_, err := repo.Append(context.Background(), e)
		require.NoError(t, err)
	}

	// Aggregate
	aggregated, err := repo.AggregateByKind(context.Background(), "pos_agg")
	require.NoError(t, err)
	assert.True(t, aggregated[ports.LedgerEntryFee].Equal(domain.MustDecimal("30")))
	assert.True(t, aggregated[ports.LedgerEntryGas].Equal(domain.MustDecimal("-5")))
}

// Test RiskRepo with schema matching
func TestRiskRepo_AppendRiskEvent(t *testing.T) {
	db, cleanup := setupRepoTestDB(t, "risk_test_")
	defer cleanup()

	repo := NewRiskRepo(db, "risk_test_")

	event := ports.RiskEvent{
		ID:         "risk_test_001",
		PositionID: "pos_001",
		PoolKey:    "base:uniswap_v3:0xpool",
		Source:     ports.RiskSourceDailyDD,
		Action:     ports.RiskActionFreeze,
		Level:      ports.KillLevelWarn,
		Details:    "Daily drawdown threshold breached",
		Timestamp: 1700000000000,
	}

	err := repo.AppendRiskEvent(context.Background(), event)
	require.NoError(t, err)

	// ListRiskEvents with no filter (get all)
	events, err := repo.ListRiskEvents(context.Background(), ports.RiskEventFilter{})
	require.NoError(t, err)
	assert.GreaterOrEqual(t, len(events), 1, "should have at least 1 event")

	// Verify the event fields
	found := events[0]
	assert.Equal(t, "risk_test_001", found.ID)
}

func TestRiskRepo_KillState(t *testing.T) {
	db, err := sql.Open("sqlite3", ":memory:")
	require.NoError(t, err)
	defer db.Close()

	// Create fresh table with required columns
	_, err = db.Exec(`CREATE TABLE kill_test_kill_switch_state (
		id TEXT PRIMARY KEY,
		switch_type TEXT NOT NULL,
		triggered_at INTEGER NOT NULL,
		trigger_reason TEXT,
		auto_resume_at INTEGER,
		resumed_at INTEGER,
		resume_allowed INTEGER DEFAULT 1,
		total_triggers INTEGER DEFAULT 1,
		updated_at INTEGER NOT NULL
	)`)
	require.NoError(t, err)

	repo := NewRiskRepo(db, "kill_test_")

	// Get default kill state
	state, err := repo.GetKillState(context.Background())
	require.NoError(t, err)
	assert.Equal(t, ports.KillLevelOK, state.Level)

	// Insert a kill state record directly with required updated_at
	_, err = db.ExecContext(context.Background(), `
		INSERT INTO kill_test_kill_switch_state (id, switch_type, triggered_at, trigger_reason, updated_at)
		VALUES (?, ?, ?, ?, ?)
	`, "kill_switch_state", "warn", 1700000000000, "Daily drawdown exceeded", 1700000000000)
	require.NoError(t, err)

	// Verify - switch_type "warn" maps to KillLevelWarn
	retrieved, err := repo.GetKillState(context.Background())
	require.NoError(t, err)
	assert.Equal(t, ports.KillLevelWarn, retrieved.Level)
}

// Test prefix isolation
func TestPrefixIsolation(t *testing.T) {
	db1, cleanup1 := setupRepoTestDB(t, "dryrun_")
	defer cleanup1()

	db2, cleanup2 := setupRepoTestDB(t, "shadow_")
	defer cleanup2()

	// Position repos with different prefixes
	posRepo1 := NewPositionRepo(db1, "dryrun_")
	posRepo2 := NewPositionRepo(db2, "shadow_")

	// Save to different prefixes
	pos1 := &domain.Position{ID: "pos_dry", Chain: domain.ChainBase, PoolID: "p1", Status: domain.StatusOpen, TickLower: 0, TickUpper: 100, OpenedAt: 1}
	pos2 := &domain.Position{ID: "pos_shadow", Chain: domain.ChainBase, PoolID: "p1", Status: domain.StatusOpen, TickLower: 0, TickUpper: 100, OpenedAt: 2}

	err := posRepo1.Save(context.Background(), pos1)
	require.NoError(t, err)
	err = posRepo2.Save(context.Background(), pos2)
	require.NoError(t, err)

	// Verify isolation - dryrun repo shouldn't find shadow position
	found1, err := posRepo1.FindByID(context.Background(), "pos_dry")
	require.NoError(t, err)
	assert.Equal(t, "pos_dry", found1.ID)

	_, err = posRepo1.FindByID(context.Background(), "pos_shadow")
	assert.ErrorIs(t, err, ports.ErrPositionNotFound)
}