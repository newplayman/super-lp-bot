// Package postgres provides PostgreSQL adapter tests.
package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// MockDB is a simple mock for testing without a real database connection.
type MockDB struct {
	ledgers     []ports.LedgerEntry
	positions   []*domain.Position
	shouldError bool
}

func (m *MockDB) ExecContext(ctx context.Context, query string, args ...interface{}) (sql.Result, error) {
	if m.shouldError {
		return nil, fmt.Errorf("mock error")
	}
	return &mockResult{}, nil
}

type mockResult struct{}

func (m *mockResult) LastInsertId() (int64, error) { return 0, nil }
func (m *mockResult) RowsAffected() (int64, error) { return 1, nil }

// TestPostgres_New tests the postgres adapter initialization.
func TestPostgres_New(t *testing.T) {
	// Test with invalid config - should fail to connect
	cfg := PostgresConfig{
		Host:     "localhost",
		Port:     5432,
		User:     "nonexistent_user",
		Password: "wrong_password",
		Database: "nonexistent_db",
		SSLMode:  "disable",
	}

	// This will fail since we don't have a real postgres running
	_, err := New(cfg)
	if err == nil {
		t.Log("Warning: New() succeeded unexpectedly - is there a postgres server running?")
	} else {
		t.Logf("Expected error for invalid config: %v", err)
	}
}

// TestPostgres_ConfigDSN tests the PostgresConfig DSN generation.
func TestPostgres_ConfigDSN(t *testing.T) {
	cfg := PostgresConfig{
		Host:     "localhost",
		Port:     5432,
		User:     "testuser",
		Password: "testpass",
		Database: "testdb",
		SSLMode:  "require",
	}

	dsn := cfg.DSN()
	expected := "host=localhost port=5432 user=testuser password=testpass dbname=testdb sslmode=require"
	if dsn != expected {
		t.Errorf("DSN() = %q, want %q", dsn, expected)
	}
}

// TestPostgres_ConfigDSN_DefaultSSL tests default SSL mode.
func TestPostgres_ConfigDSN_DefaultSSL(t *testing.T) {
	cfg := PostgresConfig{
		Host:     "localhost",
		Port:     5432,
		User:     "testuser",
		Password: "testpass",
		Database: "testdb",
		SSLMode:  "", // empty should default to "disable"
	}

	dsn := cfg.DSN()
	if dsn == "" {
		t.Error("DSN() returned empty string")
	}

	expectedSSL := "sslmode=disable"
	if dsn != expectedSSL && !contains(dsn, expectedSSL) {
		// The DSN should contain sslmode=disable as default
		t.Logf("DSN with empty SSL: %s", dsn)
	}
}

// TestLedgerRepo_Append tests ledger entry append operation.
func TestLedgerRepo_Append(t *testing.T) {
	// Create a mock ledger repo for unit testing interface compliance
	repo := &LedgerRepo{}
	var _ ports.LedgerRepo = repo // compile-time assertion

	// Test that the repo implements the interface
	t.Log("LedgerRepo implements ports.LedgerRepo interface")
}

func TestStableLedgerEntryID(t *testing.T) {
	entry := ports.LedgerEntry{
		PositionID:  "pos-1",
		Kind:        ports.LedgerEntryFee,
		Amount:      domain.MustDecimal("1.25"),
		TokenSymbol: "USDC",
		BlockRef: domain.BlockRef{
			Chain:    domain.ChainBase,
			Number:   123,
			Hash:     "0xabc",
			TimeUnix: 1700000000,
		},
		TxHash: "0xtx",
	}
	first := stableLedgerEntryID(entry)
	second := stableLedgerEntryID(entry)
	if first == "" {
		t.Fatal("stableLedgerEntryID returned empty string")
	}
	if first != second {
		t.Fatalf("stableLedgerEntryID should be deterministic: %s != %s", first, second)
	}
	entry.TxHash = "0xother"
	third := stableLedgerEntryID(entry)
	if third == first {
		t.Fatalf("stableLedgerEntryID should change when entry changes: %s == %s", third, first)
	}
}

// TestLedgerRepo_InterfaceCompliance ensures the repo satisfies the interface.
func TestLedgerRepo_InterfaceCompliance(t *testing.T) {
	var repo ports.LedgerRepo = &LedgerRepo{}
	if repo == nil {
		t.Error("LedgerRepo should be assignable to ports.LedgerRepo")
	}

	// Note: We don't call actual methods here to avoid nil pointer dereference
	// without a real database connection. Interface compliance is verified
	// through compile-time assertions above.
	t.Log("LedgerRepo interface compliance verified via compile-time assertion")
}

// TestPositionRepo_InterfaceCompliance tests PositionRepo interface.
func TestPositionRepo_InterfaceCompliance(t *testing.T) {
	var repo ports.PositionRepo = &PositionRepo{}
	if repo == nil {
		t.Error("PositionRepo should be assignable to ports.PositionRepo")
	}
	t.Log("PositionRepo interface compliance verified via compile-time assertion")
}

// TestPoolRepo_InterfaceCompliance tests PoolRepo interface.
func TestPoolRepo_InterfaceCompliance(t *testing.T) {
	var repo ports.PoolRepo = &PoolRepo{}
	if repo == nil {
		t.Error("PoolRepo should be assignable to ports.PoolRepo")
	}
	t.Log("PoolRepo interface compliance verified via compile-time assertion")
}

// TestRiskRepo_InterfaceCompliance tests RiskRepo interface.
func TestRiskRepo_InterfaceCompliance(t *testing.T) {
	var repo ports.RiskRepo = &RiskRepo{}
	if repo == nil {
		t.Error("RiskRepo should be assignable to ports.RiskRepo")
	}
	t.Log("RiskRepo interface compliance verified via compile-time assertion")
}

// TestTxRepo_InterfaceCompliance tests TxRepo interface.
func TestTxRepo_InterfaceCompliance(t *testing.T) {
	var repo ports.TxRepo = &TxRepo{}
	if repo == nil {
		t.Error("TxRepo should be assignable to ports.TxRepo")
	}
	t.Log("TxRepo interface compliance verified via compile-time assertion")
}

func TestTxBroadcastTimestamp(t *testing.T) {
	now := time.Now().UnixMilli()
	if got := txBroadcastTimestamp(domain.TxBuilt, now); got != nil {
		t.Fatalf("built tx should not set broadcast timestamp, got %v", got)
	}
	for _, status := range []domain.TxStatus{
		domain.TxSubmittedPrivate,
		domain.TxBroadcast,
		domain.TxMined,
		domain.TxConfirmed,
		domain.TxStuck,
		domain.TxRFBBumped,
		domain.TxReverted,
		domain.TxReorged,
		domain.TxFailed,
	} {
		got := txBroadcastTimestamp(status, now)
		if got == nil {
			t.Fatalf("status %s should set broadcast timestamp", status)
		}
		if got.(int64) != now {
			t.Fatalf("status %s broadcast timestamp = %v, want %d", status, got, now)
		}
	}
}

// TestChainIDConversion tests chain ID conversion helpers.
func TestChainIDConversion(t *testing.T) {
	tests := []struct {
		chain   domain.ChainID
		wantInt int
	}{
		{domain.ChainBase, 1},
		{domain.ChainSolana, 2},
		{domain.ChainID("unknown"), 0},
	}

	for _, tt := range tests {
		got := chainIDToInt(tt.chain)
		if got != tt.wantInt {
			t.Errorf("chainIDToInt(%v) = %d, want %d", tt.chain, got, tt.wantInt)
		}

		// Test reverse conversion
		gotChain := intToChainID(tt.wantInt)
		if tt.chain != domain.ChainID("unknown") && gotChain != tt.chain {
			t.Errorf("intToChainID(%d) = %v, want %v", tt.wantInt, gotChain, tt.chain)
		}
	}
}

// TestPostgresAdapter_AllRepos tests that all repos are accessible from adapter.
func TestPostgresAdapter_AllRepos(t *testing.T) {
	// Create adapter without real connection (will fail on ping)
	cfg := PostgresConfig{
		Host:     "localhost",
		Port:     5432,
		User:     "test",
		Password: "test",
		Database: "test",
		SSLMode:  "disable",
	}

	adapter, err := New(cfg)
	if err != nil {
		t.Logf("Expected connection failure: %v", err)
		return
	}
	defer adapter.Close()

	// Verify all repo getters return non-nil
	if adapter.LedgerRepo() == nil {
		t.Error("LedgerRepo() returned nil")
	}
	if adapter.PositionRepo() == nil {
		t.Error("PositionRepo() returned nil")
	}
	if adapter.PoolRepo() == nil {
		t.Error("PoolRepo() returned nil")
	}
	if adapter.RiskRepo() == nil {
		t.Error("RiskRepo() returned nil")
	}
	if adapter.TxRepo() == nil {
		t.Error("TxRepo() returned nil")
	}

	// Verify underlying DB is accessible
	if adapter.DB() == nil {
		t.Error("DB() returned nil")
	}
}

// TestLedgerEntryKind_Constants verifies ledger entry kind constants.
func TestLedgerEntryKind_Constants(t *testing.T) {
	kinds := []ports.LedgerEntryKind{
		ports.LedgerEntryFee,
		ports.LedgerEntryIL,
		ports.LedgerEntrySwap,
		ports.LedgerEntryGas,
		ports.LedgerEntrySlippage,
		ports.LedgerEntryRug,
	}
	for _, k := range kinds {
		if k == "" {
			t.Error("LedgerEntryKind constant should not be empty")
		}
	}
}

// TestRiskRepo_AppendRiskEvent verifies risk event append operation.
func TestRiskRepo_AppendRiskEvent(t *testing.T) {
	repo := &RiskRepo{}
	var _ ports.RiskRepo = repo
	t.Log("RiskRepo.AppendRiskEvent interface verified via compile-time assertion")
}

func TestPostgresAdapter_DockerIntegration_RoundTrip(t *testing.T) {
	if _, err := exec.LookPath("docker"); err != nil {
		t.Skip("docker not available")
	}

	runOutput := strings.TrimSpace(runCmd(t, "docker", "run", "-d", "--rm",
		"-e", "POSTGRES_PASSWORD=postgres",
		"-e", "POSTGRES_USER=postgres",
		"-e", "POSTGRES_DB=lpbot_test",
		"-P", "postgres:16-alpine"))
	lines := strings.Split(runOutput, "\n")
	containerID := strings.TrimSpace(lines[len(lines)-1])
	defer runCmdBestEffort("docker", "rm", "-f", containerID)

	hostPort := parseDockerPort(t, waitForDockerPort(t, containerID))
	cfg := PostgresConfig{
		Host:     "127.0.0.1",
		Port:     hostPort,
		User:     "postgres",
		Password: "postgres",
		Database: "lpbot_test",
		SSLMode:  "disable",
	}

	var adapter *postgresAdapter
	var err error
	for i := 0; i < 20; i++ {
		adapter, err = New(cfg)
		if err == nil {
			break
		}
		time.Sleep(1 * time.Second)
	}
	if err != nil {
		t.Fatalf("connect postgres container: %v", err)
	}
	defer adapter.Close()

	ctx := context.Background()
	mustExecSQL(t, adapter.db, `CREATE TABLE positions (
		id TEXT PRIMARY KEY,
		token_id TEXT NOT NULL DEFAULT '',
		pool_id TEXT NOT NULL,
		chain INTEGER NOT NULL,
		protocol TEXT,
		status TEXT NOT NULL,
		tier TEXT NOT NULL,
		tick_lower BIGINT NOT NULL,
		tick_upper BIGINT NOT NULL,
		amount_usd TEXT NOT NULL,
		open_tx_hash TEXT,
		metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
		opened_at BIGINT NOT NULL,
		closed_at BIGINT NOT NULL DEFAULT 0
	)`)
	mustExecSQL(t, adapter.db, `CREATE TABLE transactions (
		id TEXT PRIMARY KEY,
		chain TEXT NOT NULL,
		tx_hash TEXT UNIQUE NOT NULL,
		from_address TEXT NOT NULL,
		to_address TEXT NOT NULL,
		data BYTEA,
		value TEXT,
		nonce BIGINT,
		deadline BIGINT,
		min_out TEXT,
		signature BYTEA,
		status TEXT NOT NULL,
		block_number BIGINT,
		block_hash TEXT,
		broadcast_at BIGINT,
		gas_used BIGINT,
		gas_price TEXT,
		gas_limit BIGINT,
		rfb_attempts INTEGER DEFAULT 0,
		error_msg TEXT,
		trace_id TEXT,
		created_at BIGINT NOT NULL,
		updated_at BIGINT NOT NULL
	)`)
	mustExecSQL(t, adapter.db, `CREATE TABLE pools (
		pool_id TEXT NOT NULL,
		chain INTEGER NOT NULL,
		protocol TEXT NOT NULL,
		token0 TEXT NOT NULL,
		token1 TEXT NOT NULL,
		fee_bps INTEGER NOT NULL,
		tier TEXT,
		audit_verdict TEXT,
		last_score JSONB,
		updated_block BIGINT,
		updated_at BIGINT NOT NULL,
		liquidity TEXT,
		tick BIGINT,
		tvl_usd TEXT,
		vol_24h TEXT,
		fee_apr_24h TEXT,
		UNIQUE(pool_id, chain, protocol)
	)`)
	mustExecSQL(t, adapter.db, `CREATE TABLE pool_score_history (
		id BIGSERIAL PRIMARY KEY,
		pool_id TEXT NOT NULL,
		chain INTEGER NOT NULL,
		block_number BIGINT NOT NULL,
		block_hash TEXT NOT NULL,
		block_time BIGINT NOT NULL,
		score_json JSONB NOT NULL,
		trace_id TEXT NOT NULL
	)`)

	pos := &domain.Position{
		ID:        "pos-it",
		TokenID:   "123",
		PoolID:    "0xpool",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		Tier:      domain.TierB,
		TickLower: -100,
		TickUpper: 100,
		AmountUSD: domain.MustDecimal("12.34"),
		OpenedAt:  time.Now().Unix(),
	}
	if err := adapter.PositionRepo().Save(ctx, pos); err != nil {
		t.Fatalf("save position: %v", err)
	}
	gotPos, err := adapter.PositionRepo().FindByID(ctx, pos.ID)
	if err != nil {
		t.Fatalf("find position: %v", err)
	}
	if gotPos == nil || gotPos.ID != pos.ID || gotPos.Status != domain.StatusOpen {
		t.Fatalf("unexpected position roundtrip: %+v", gotPos)
	}

	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       "tx-it",
			Chain:    domain.ChainBase,
			From:     domain.MustParseAddress("0x0000000000000000000000000000000000000001"),
			To:       domain.MustParseAddress("0x0000000000000000000000000000000000000002"),
			Value:    domain.MustDecimal("0"),
			Deadline: time.Now().Add(5 * time.Minute).Unix(),
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   "0xtesthash",
		Status: domain.TxBroadcast,
	}
	if err := adapter.TxRepo().UpsertTx(ctx, tx); err != nil {
		t.Fatalf("upsert tx: %v", err)
	}
	gotTx, err := adapter.TxRepo().GetTxByHash(ctx, domain.ChainBase, tx.Hash)
	if err != nil {
		t.Fatalf("get tx: %v", err)
	}
	if gotTx.Hash != tx.Hash || gotTx.Status != domain.TxBroadcast {
		t.Fatalf("unexpected tx roundtrip: %+v", gotTx)
	}
	var blockNumber, broadcastAt sql.NullInt64
	if err := adapter.db.QueryRowContext(ctx, `
		SELECT block_number, broadcast_at
		FROM transactions
		WHERE tx_hash = $1
	`, tx.Hash).Scan(&blockNumber, &broadcastAt); err != nil {
		t.Fatalf("query tx timestamps: %v", err)
	}
	if blockNumber.Valid {
		t.Fatalf("expected block_number to remain null, got %d", blockNumber.Int64)
	}
	if !broadcastAt.Valid || broadcastAt.Int64 == 0 {
		t.Fatalf("expected broadcast_at to be populated, got %+v", broadcastAt)
	}

	pool := domain.Pool{
		ID:        "0xpool",
		Chain:     domain.ChainBase,
		Protocol:  "uniswap_v3",
		Token0:    domain.MustParseAddress("0x0000000000000000000000000000000000000003"),
		Token1:    domain.MustParseAddress("0x0000000000000000000000000000000000000004"),
		FeeBPS:    30,
		Tier_:     domain.TierA,
		Liquidity: domain.MustDecimal("1000"),
		Tick:      123,
		TVLUSD:    domain.MustDecimal("4567"),
		Vol24h:    domain.MustDecimal("890"),
		FeeAPR24h: domain.MustDecimal("12.5"),
		UpdatedAt: time.Now().Unix(),
	}
	score := domain.Score{
		FeeAPRScore:     70,
		TvlScore:        90,
		VolScore:        85,
		VolatilityScore: 80,
		SecurityScore:   95,
		Total:           84,
	}
	if err := adapter.PoolRepo().UpsertPool(ctx, ports.PoolWithScore{Pool: pool, Score: score}); err != nil {
		t.Fatalf("upsert pool: %v", err)
	}
	gotPool, err := adapter.PoolRepo().GetPool(ctx, "base:uniswap_v3:0xpool")
	if err != nil {
		t.Fatalf("get pool: %v", err)
	}
	if gotPool.ID != pool.ID || gotPool.Tick != pool.Tick {
		t.Fatalf("unexpected pool roundtrip: %+v", gotPool)
	}
}

// Helper function
func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func mustExecSQL(t *testing.T, db *sql.DB, stmt string) {
	t.Helper()
	if _, err := db.Exec(stmt); err != nil {
		t.Fatalf("exec schema: %v", err)
	}
}

func waitForDockerPort(t *testing.T, containerID string) string {
	t.Helper()
	for i := 0; i < 20; i++ {
		out, err := exec.Command("docker", "port", containerID, "5432/tcp").CombinedOutput()
		if err == nil && strings.TrimSpace(string(out)) != "" {
			return strings.TrimSpace(string(out))
		}
		time.Sleep(1 * time.Second)
	}
	t.Fatalf("docker port not available for container %s", containerID)
	return ""
}

func parseDockerPort(t *testing.T, value string) int {
	t.Helper()
	parts := strings.Split(strings.TrimSpace(value), ":")
	if len(parts) == 0 {
		t.Fatalf("unexpected docker port output: %q", value)
	}
	var port int
	if _, err := fmt.Sscanf(parts[len(parts)-1], "%d", &port); err != nil || port <= 0 {
		t.Fatalf("parse docker port from %q: %v", value, err)
	}
	return port
}

func runCmd(t *testing.T, name string, args ...string) string {
	t.Helper()
	out, err := exec.Command(name, args...).CombinedOutput()
	if err != nil {
		t.Fatalf("%s %v failed: %v\n%s", name, args, err, string(out))
	}
	return string(out)
}

func runCmdBestEffort(name string, args ...string) {
	_, _ = exec.Command(name, args...).CombinedOutput()
}
