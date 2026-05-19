// Package main provides the lpbot-backtest CLI for Phase 0 validation.
// It simulates LP positions over historical data and compares with real fee data.
package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"os"
	"time"

	_ "github.com/mattn/go-sqlite3"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

const Version = "0.0.1-phase0"

// Config holds all command-line configuration for the backtest.
type Config struct {
	Pool      string    // pool address
	Chain     string    // chain (base/solana)
	From      time.Time // start date
	To        time.Time // end date
	RangeMode string    // symmetric/increasing/decreasing
	RangeK    float64   // k-sigma for symmetric mode
	Tier      string    // tier A/B/C
	OutputDir string    // output directory
	CacheDB   string    // SQLite cache database path
}

// ParseFlags parses command-line flags and returns the Config.
func ParseFlags() (*Config, error) {
	cfg := &Config{}

	flag.StringVar(&cfg.Pool, "pool", "", "Pool address (required)")
	flag.StringVar(&cfg.Chain, "chain", "base", "Chain (base/solana)")
	fromStr := flag.String("from", "", "Start date (RFC3339 format, required)")
	toStr := flag.String("to", "", "End date (RFC3339 format, required)")
	flag.StringVar(&cfg.RangeMode, "range-mode", "symmetric", "Range mode: symmetric/increasing/decreasing")
	flag.Float64Var(&cfg.RangeK, "range-k-sigma", 1.5, "k-sigma multiplier for symmetric mode")
	flag.StringVar(&cfg.Tier, "tier", "A", "Tier A/B/C")
	flag.StringVar(&cfg.OutputDir, "output", "./backtest_output", "Output directory")
	flag.StringVar(&cfg.CacheDB, "cache-db", "", "SQLite cache database path")

	flag.Parse()

	// Validate required flags
	if cfg.Pool == "" {
		return nil, fmt.Errorf("--pool is required")
	}
	if cfg.Chain != "base" && cfg.Chain != "solana" {
		return nil, fmt.Errorf("--chain must be 'base' or 'solana'")
	}
	if *fromStr == "" {
		return nil, fmt.Errorf("--from is required")
	}
	if *toStr == "" {
		return nil, fmt.Errorf("--to is required")
	}

	// Parse dates
	from, err := time.Parse(time.RFC3339, *fromStr)
	if err != nil {
		return nil, fmt.Errorf("invalid --from format: %w", err)
	}
	cfg.From = from

	to, err := time.Parse(time.RFC3339, *toStr)
	if err != nil {
		return nil, fmt.Errorf("invalid --to format: %w", err)
	}
	cfg.To = to

	if cfg.From.After(cfg.To) {
		return nil, fmt.Errorf("--from must be before --to")
	}

	// Validate range mode
	switch cfg.RangeMode {
	case "symmetric", "increasing", "decreasing":
		// valid
	default:
		return nil, fmt.Errorf("--range-mode must be symmetric, increasing, or decreasing")
	}

	// Validate tier
	if cfg.Tier != "A" && cfg.Tier != "B" && cfg.Tier != "C" {
		return nil, fmt.Errorf("--tier must be A, B, or C")
	}

	// Validate range k
	if cfg.RangeK <= 0 {
		return nil, fmt.Errorf("--range-k-sigma must be positive")
	}

	return cfg, nil
}

// validatePool is a helper to validate the pool exists and is accessible.
func validatePool(ctx context.Context, poolID string, chain domain.ChainID) error {
	// In Phase 0, we accept any pool address - actual validation happens in the loader
	return nil
}

// createOutputDir creates the output directory if it doesn't exist.
func createOutputDir(dir string) error {
	return os.MkdirAll(dir, 0755)
}

// openCacheDB opens or creates the SQLite cache database.
func openCacheDB(path string) (*sql.DB, error) {
	if path == "" {
		// Use a temporary database in the output directory
		// This will be set by the caller
		return nil, nil
	}

	db, err := sql.Open("sqlite3", path)
	if err != nil {
		return nil, fmt.Errorf("open cache db: %w", err)
	}

	// Create cache tables
	if err := createCacheTables(db); err != nil {
		return nil, fmt.Errorf("create cache tables: %w", err)
	}

	return db, nil
}

// createCacheTables creates the necessary tables for caching historical data.
func createCacheTables(db *sql.DB) error {
	schema := `
	CREATE TABLE IF NOT EXISTS cache_swaps (
		id TEXT PRIMARY KEY,
		pool_id TEXT NOT NULL,
		timestamp INTEGER NOT NULL,
		block_number INTEGER NOT NULL,
		token0_in TEXT NOT NULL,
		token1_in TEXT NOT NULL,
		token0_out TEXT NOT NULL,
		token1_out TEXT NOT NULL,
		fee TEXT NOT NULL,
		tx_hash TEXT NOT NULL
	);

	CREATE TABLE IF NOT EXISTS cache_pool_states (
		id TEXT PRIMARY KEY,
		pool_id TEXT NOT NULL,
		timestamp INTEGER NOT NULL,
		block_number INTEGER NOT NULL,
		tick INTEGER NOT NULL,
		liquidity TEXT NOT NULL,
		sqrt_price_x96 TEXT,
		fee_growth_global_0 TEXT,
		fee_growth_global_1 TEXT
	);

	CREATE INDEX IF NOT EXISTS idx_cache_swaps_pool_timestamp ON cache_swaps(pool_id, timestamp);
	CREATE INDEX IF NOT EXISTS idx_cache_pool_states_pool_timestamp ON cache_pool_states(pool_id, timestamp);
	`

	_, err := db.Exec(schema)
	return err
}

// DataLoader defines the interface for loading historical data.
type DataLoader interface {
	LoadSwaps(ctx context.Context, pool domain.Pool, from, to time.Time) ([]ports.Swap, error)
	LoadPoolStates(ctx context.Context, pool domain.Pool, from, to time.Time, step time.Duration) ([]domain.PoolState, error)
	LoadCollectedFees(ctx context.Context, pool domain.Pool, from, to time.Time) (domain.Decimal, error)
}

// Run executes the backtest with the given configuration.
func Run(ctx context.Context, cfg *Config, loader DataLoader, ledgerRepo ports.LedgerRepo) error {
	fmt.Printf("lpbot-backtest v%s\n", Version)
	fmt.Printf("Pool: %s\n", cfg.Pool)
	fmt.Printf("Chain: %s\n", cfg.Chain)
	fmt.Printf("Period: %s -> %s\n", cfg.From.Format(time.RFC3339), cfg.To.Format(time.RFC3339))
	fmt.Printf("Range mode: %s (k=%.2f)\n", cfg.RangeMode, cfg.RangeK)
	fmt.Printf("Tier: %s\n", cfg.Tier)
	fmt.Printf("Output: %s\n", cfg.OutputDir)
	fmt.Println()

	// Create output directory
	if err := createOutputDir(cfg.OutputDir); err != nil {
		return fmt.Errorf("create output dir: %w", err)
	}

	// Parse chain
	chain, err := domain.ParseChainID(cfg.Chain)
	if err != nil {
		return fmt.Errorf("parse chain: %w", err)
	}

	// Create pool object
	pool := domain.Pool{
		ID:     cfg.Pool,
		Chain:  chain,
		Token0: domain.MustParseAddress("0x0000000000000000000000000000000000000000"),
		Token1: domain.MustParseAddress("0x0000000000000000000000000000000000000000"),
	}

	// Validate pool
	if err := validatePool(ctx, cfg.Pool, chain); err != nil {
		return fmt.Errorf("validate pool: %w", err)
	}

	// Load historical data
	fmt.Println("Loading historical data...")
	swaps, err := loader.LoadSwaps(ctx, pool, cfg.From, cfg.To)
	if err != nil {
		return fmt.Errorf("load swaps: %w", err)
	}
	fmt.Printf("  Loaded %d swaps\n", len(swaps))

	// Load pool states at 1-hour intervals
	step := time.Hour
	poolStates, err := loader.LoadPoolStates(ctx, pool, cfg.From, cfg.To, step)
	if err != nil {
		return fmt.Errorf("load pool states: %w", err)
	}
	fmt.Printf("  Loaded %d pool states\n", len(poolStates))

	// Load ground truth fees
	fmt.Println("Loading ground truth fees...")
	groundTruthFees, err := loader.LoadCollectedFees(ctx, pool, cfg.From, cfg.To)
	if err != nil {
		fmt.Printf("  Warning: could not load ground truth: %v\n", err)
		groundTruthFees = domain.Decimal{}
	} else {
		fmt.Printf("  Ground truth fees: %s\n", groundTruthFees.String())
	}

	// Simulate position
	fmt.Println("\nSimulating position...")
	sim := NewSimulator(cfg.RangeMode, cfg.RangeK)
	pos := sim.CreatePosition(pool, cfg.From)

	// Run simulation
	result, err := sim.Simulate(ctx, pos, swaps, poolStates, ledgerRepo)
	if err != nil {
		return fmt.Errorf("simulation: %w", err)
	}

	// Write ledger entries
	fmt.Println("\nWriting PnL ledger...")
	if ledgerRepo != nil {
		if err := WriteLedger(ctx, ledgerRepo, result); err != nil {
			return fmt.Errorf("write ledger: %w", err)
		}
	}

	// Compare results
	fmt.Println("\nComparing with ground truth...")
	comparison, err := Compare(result.SimulatedFees, groundTruthFees)
	if err != nil {
		return fmt.Errorf("compare: %w", err)
	}

	// Generate output files
	fmt.Println("\nGenerating output files...")
	if err := GenerateOutputs(cfg.OutputDir, result, comparison, pool); err != nil {
		return fmt.Errorf("generate outputs: %w", err)
	}

	// Print summary
	fmt.Println("\n=== Backtest Summary ===")
	fmt.Printf("Simulated fees:    %s\n", result.SimulatedFees.String())
	fmt.Printf("Ground truth fees: %s\n", groundTruthFees.String())
	fmt.Printf("Error:             %.2f%%\n", comparison.ErrorPct*100)
	fmt.Printf("Verdict:           %s\n", comparison.Verdict)
	fmt.Printf("\nOutput files generated in: %s\n", cfg.OutputDir)

	return nil
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--version" {
		fmt.Println(Version)
		os.Exit(0)
	}

	cfg, err := ParseFlags()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n\n", err)
		flag.Usage()
		os.Exit(1)
	}

	ctx := context.Background()

	// Open cache DB if specified
	var cacheDB *sql.DB
	if cfg.CacheDB != "" {
		cacheDB, err = openCacheDB(cfg.CacheDB)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error opening cache DB: %v\n", err)
			os.Exit(1)
		}
		defer cacheDB.Close()
	}

	// Create data loader
	var loader DataLoader = NewCachedLoader(cacheDB)

	if err := Run(ctx, cfg, loader, nil); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}