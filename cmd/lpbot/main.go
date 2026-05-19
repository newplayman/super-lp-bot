// Package main provides the main entry point for lpbot.
// It supports three build modes: dryrun, shadow, and live.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/platform/log"
	"go.uber.org/zap"
)

const Version = "0.4.0"

var (
	// Build tags for mode-specific compilation
	// These are set by the build system via -ldflags
	BuildMode   = "dev"
	BuildCommit = "local"
	BuildDate   = ""
)

// setupSignalHandling configures graceful shutdown on SIGINT/SIGTERM.
func setupSignalHandling() (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		cancel()
	}()
	return ctx, cancel
}

// Run executes the main application loop.
// Returns 0 on success, non-zero on failure.
func Run(ctx context.Context, logger *zap.Logger, cfg *config.Config) int {
	logger.Info("lpbot starting",
		zap.String("version", Version),
		zap.String("mode", BuildMode),
		zap.String("commit", BuildCommit),
	)

	// Validate mode-specific settings
	if err := validateMode(); err != nil {
		logger.Error("mode validation failed", zap.Error(err))
		return 1
	}

	// Initialize adapters (RPC, store, wallet, bus, datasource)
	rpc, err := initRPCProviders(ctx, logger, cfg)
	if err != nil {
		logger.Error("failed to initialize RPC providers", zap.Error(err))
		return 1
	}

	store, err := initStore(ctx, logger, cfg)
	if err != nil {
		logger.Error("failed to initialize store", zap.Error(err))
		return 1
	}

	datasource, err := initDatasource(ctx, logger, cfg)
	if err != nil {
		logger.Error("failed to initialize datasource", zap.Error(err))
		return 1
	}

	wallet, err := initWallet(ctx, logger, cfg)
	if err != nil {
		logger.Error("failed to initialize wallet", zap.Error(err))
		return 1
	}

	bus, err := initBus(ctx, logger, cfg)
	if err != nil {
		logger.Error("failed to initialize bus", zap.Error(err))
		return 1
	}

	logger.Info("adapters initialized",
		zap.Any("rpc_providers", rpc),
		zap.Any("store", store),
		zap.Any("datasource", datasource),
		zap.Any("wallet", wallet),
		zap.Any("bus", bus),
	)

	// Initialize core modules (scanner, strategy, risk, execution, pnl, audit)
	_, _ = initScanner(ctx, logger, cfg, datasource)
	_, _ = initStrategy(ctx, logger, cfg, store, rpc)
	_ = initRisk(ctx, logger, cfg, store)
	_ = initExecution(ctx, logger, cfg, store, rpc, wallet, bus)
	_ = initPnL(ctx, logger, cfg, store)
	_ = initAudit(ctx, logger, cfg, store, rpc)

	logger.Info("core modules initialized")

	// Main loop
	logger.Info("entering main loop")
	<-ctx.Done()
	logger.Info("shutdown complete")
	return 0
}

// initRPCProviders initializes round-robin RPC providers for each chain.
func initRPCProviders(ctx context.Context, logger *zap.Logger, cfg *config.Config) (map[string]interface{}, error) {
	// TODO: Implement actual RPC provider initialization
	// Example: rpc.NewRoundRobinProvider(cfg.Chains.Base.RPCPrimary)
	logger.Info("RPC providers would be initialized from config")
	return map[string]interface{}{"base": nil, "solana": nil}, nil
}

// initStore initializes the data store (SQLite for shadow, Postgres for live).
func initStore(ctx context.Context, logger *zap.Logger, cfg *config.Config) (interface{}, error) {
	// TODO: Implement actual store initialization
	logger.Info("store would be initialized", zap.String("backend", cfg.Store.Backend))
	return nil, nil
}

// initDatasource initializes the data source for pool discovery.
func initDatasource(ctx context.Context, logger *zap.Logger, cfg *config.Config) (interface{}, error) {
	// TODO: Implement actual datasource initialization
	// Example: geckoterminal.NewAdapter()
	logger.Info("datasource would be initialized")
	return nil, nil
}

// initWallet initializes the wallet (keystore for live, none for shadow/dryrun).
func initWallet(ctx context.Context, logger *zap.Logger, cfg *config.Config) (interface{}, error) {
	// TODO: Implement actual wallet initialization
	logger.Info("wallet would be initialized", zap.String("backend", cfg.Wallet.Backend))
	return nil, nil
}

// initBus initializes the event bus for inter-module communication.
func initBus(ctx context.Context, logger *zap.Logger, cfg *config.Config) (interface{}, error) {
	// TODO: Implement actual bus initialization
	logger.Info("bus would be initialized", zap.String("backend", cfg.Bus.Backend))
	return nil, nil
}

// initScanner initializes the pool scanner module.
func initScanner(ctx context.Context, logger *zap.Logger, cfg *config.Config, datasource interface{}) (interface{}, error) {
	// TODO: Implement actual scanner initialization
	// Example: scanner.New(scanner.Config{Datasource: datasource})
	logger.Info("scanner would be initialized")
	return nil, nil
}

// initStrategy initializes the LP strategy module.
func initStrategy(ctx context.Context, logger *zap.Logger, cfg *config.Config, store, rpc interface{}) (interface{}, error) {
	// TODO: Implement actual strategy initialization
	logger.Info("strategy would be initialized")
	return nil, nil
}

// initRisk initializes the risk management module.
func initRisk(ctx context.Context, logger *zap.Logger, cfg *config.Config, store interface{}) interface{} {
	// TODO: Implement actual risk initialization
	logger.Info("risk would be initialized", zap.Any("config", cfg.Risk))
	return nil
}

// initExecution initializes the execution module (order manager, RBF).
func initExecution(ctx context.Context, logger *zap.Logger, cfg *config.Config, store, rpc, wallet, bus interface{}) interface{} {
	// TODO: Implement actual execution initialization
	logger.Info("execution would be initialized")
	return nil
}

// initPnL initializes the PnL tracking module.
func initPnL(ctx context.Context, logger *zap.Logger, cfg *config.Config, store interface{}) interface{} {
	// TODO: Implement actual PnL initialization
	logger.Info("pnl would be initialized")
	return nil
}

// initAudit initializes the audit/reconciliation module.
func initAudit(ctx context.Context, logger *zap.Logger, cfg *config.Config, store, rpc interface{}) interface{} {
	// TODO: Implement actual audit initialization
	logger.Info("audit would be initialized")
	return nil
}

// validateMode is implemented per build tag in mode_*.go files.

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--version" {
		fmt.Printf("lpbot %s (mode: %s, commit: %s)\n", Version, BuildMode, BuildCommit)
		os.Exit(0)
	}

	if len(os.Args) > 1 && os.Args[1] == "--help" {
		flag.Usage()
		os.Exit(0)
	}

	// Parse config path
	configPath := flag.String("config", "", "Path to config file (required)")
	flag.Parse()

	if *configPath == "" {
		fmt.Fprintln(os.Stderr, "Error: --config is required")
		flag.Usage()
		os.Exit(1)
	}

	// Load configuration
	cfg, err := config.Load(*configPath, BuildMode)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading config: %v\n", err)
		os.Exit(1)
	}

	// Initialize logger with mode
	logger := log.NewLogger(cfg.Platform.LogLevel, BuildMode)
	defer logger.Sync()

	ctx, cancel := setupSignalHandling()
	defer cancel()

	code := Run(ctx, logger, cfg)
	os.Exit(code)
}