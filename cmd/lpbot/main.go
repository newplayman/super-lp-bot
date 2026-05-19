// Package main provides the main entry point for lpbot.
// It supports three build modes: dryrun, shadow, and live.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/core/strategy"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/platform/log"
	"go.uber.org/zap"
)

const Version = "0.4.0"

var (
	BuildMode   = "dev"
	BuildCommit = "local"
	BuildDate   = ""
)

// App holds all initialized components.
type App struct {
	logger     *zap.Logger
	config     *config.Config
	rpc        map[string]*rpc.RoundRobinProvider
	store      *sqlite.Store
	datasource *geckoterminal.Adapter
	scanner    scanner.Scanner
	strategy   strategy.Strategy
	cancel     context.CancelFunc
	wg         sync.WaitGroup
}

// setupSignalHandling configures graceful shutdown.
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
func Run(ctx context.Context, logger *zap.Logger, cfg *config.Config) int {
	logger.Info("lpbot starting",
		zap.String("version", Version),
		zap.String("mode", BuildMode),
		zap.String("commit", BuildCommit),
	)

	if err := validateMode(); err != nil {
		logger.Error("mode validation failed", zap.Error(err))
		return 1
	}

	app := &App{logger: logger, config: cfg}
	defer app.cleanup()

	// Initialize adapters
	if err := app.initAdapters(ctx); err != nil {
		logger.Error("failed to initialize adapters", zap.Error(err))
		return 1
	}

	// Initialize core modules
	if err := app.initCore(ctx); err != nil {
		logger.Error("failed to initialize core modules", zap.Error(err))
		return 1
	}

	logger.Info("all components initialized")

	// Start workers
	app.startWorkers(ctx)

	// Wait for shutdown signal
	<-ctx.Done()
	logger.Info("shutdown signal received")

	app.shutdown()
	return 0
}

// initAdapters initializes all external adapters.
func (app *App) initAdapters(ctx context.Context) error {
	app.logger.Info("initializing adapters...")

	// Initialize RPC providers for each chain
	app.rpc = make(map[string]*rpc.RoundRobinProvider)

	if app.config.Chains.Base.RPCPrimary != "" {
		endpoints := []string{app.config.Chains.Base.RPCPrimary}
		endpoints = append(endpoints, app.config.Chains.Base.RPCFallback...)
		if len(endpoints) == 0 {
			endpoints = rpc.BaseEndpoints // fallback to defaults
		}

		provider, err := rpc.NewRoundRobinProvider(rpc.Config{
			ChainID:   domain.ChainBase,
			Endpoints: endpoints,
		})
		if err != nil {
			return fmt.Errorf("failed to create Base RPC provider: %w", err)
		}
		app.rpc["base"] = provider
		app.logger.Info("Base RPC provider initialized",
			zap.String("primary", endpoints[0]),
			zap.Int("endpoints", len(endpoints)))
	}

	if app.config.Chains.Solana.RPCPrimary != "" {
		provider, err := rpc.NewRoundRobinProvider(rpc.Config{
			ChainID:   domain.ChainSolana,
			Endpoints: []string{app.config.Chains.Solana.RPCPrimary},
		})
		if err != nil {
			return fmt.Errorf("failed to create Solana RPC provider: %w", err)
		}
		app.rpc["solana"] = provider
	}

	// Initialize store
	store, err := sqlite.NewStore(app.config.Store.SQLitePath)
	if err != nil {
		return fmt.Errorf("failed to initialize store: %w", err)
	}
	app.store = store
	app.logger.Info("SQLite store initialized",
		zap.String("path", app.config.Store.SQLitePath))

	// Initialize datasource
	app.datasource = geckoterminal.NewAdapter()
	app.logger.Info("GeckoTerminal datasource initialized")

	return nil
}

// initCore initializes all core business logic modules.
func (app *App) initCore(ctx context.Context) error {
	app.logger.Info("initializing core modules...")

	// Initialize scanner
	app.scanner = scanner.New(scanner.Config{
		Datasource:   app.datasource,
		Chain:        domain.ChainBase,
		MinTVLUSD:    domain.MustDecimal("10000"),
		ScanInterval: 5 * time.Minute,
		// Logger: nil for now, scanner uses log.Slog internally
	})
	app.logger.Info("scanner initialized")

	// Initialize strategy
	app.strategy = strategy.New()
	app.logger.Info("strategy initialized")

	return nil
}

// startWorkers starts background workers for scanner and execution.
func (app *App) startWorkers(ctx context.Context) {
	// Scanner worker
	app.wg.Add(1)
	go func() {
		defer app.wg.Done()
		app.runScannerLoop(ctx)
	}()

	// Strategy evaluation worker (runs periodically)
	app.wg.Add(1)
	go func() {
		defer app.wg.Done()
		app.runStrategyLoop(ctx)
	}()

	app.logger.Info("workers started",
		zap.String("scanner_interval", "5m"),
		zap.String("strategy_interval", "1m"))
}

// runScannerLoop runs the scanner periodically.
func (app *App) runScannerLoop(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	app.logger.Info("scanner loop started")

	for {
		select {
		case <-ctx.Done():
			app.logger.Info("scanner loop stopped")
			return
		case <-ticker.C:
			if err := app.scanner.Run(ctx); err != nil {
				app.logger.Error("scanner run error", zap.Error(err))
			}
		}
	}
}

// runStrategyLoop runs strategy evaluation periodically.
func (app *App) runStrategyLoop(ctx context.Context) {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	app.logger.Info("strategy loop started")

	for {
		select {
		case <-ctx.Done():
			app.logger.Info("strategy loop stopped")
			return
		case <-ticker.C:
			app.evaluateStrategies(ctx)
		}
	}
}

// evaluateStrategies evaluates pools and creates positions.
func (app *App) evaluateStrategies(ctx context.Context) {
	// In dryrun/shadow mode, we simulate strategy evaluation
	// without actually sending transactions
	app.logger.Debug("strategy evaluation tick")
}

// cleanup releases resources.
func (app *App) cleanup() {
	if app.store != nil {
		app.store.Close()
	}
	for range app.rpc {
		// RPC providers don't have close methods currently
	}
}

// shutdown gracefully stops all workers.
func (app *App) shutdown() {
	app.logger.Info("stopping workers...")
	app.wg.Wait()
	app.logger.Info("all workers stopped")
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--version" {
		fmt.Printf("lpbot %s (mode: %s, commit: %s)\n", Version, BuildMode, BuildCommit)
		os.Exit(0)
	}

	if len(os.Args) > 1 && os.Args[1] == "--help" {
		flag.Usage()
		os.Exit(0)
	}

	configPath := flag.String("config", "", "Path to config file (required)")
	flag.Parse()

	if *configPath == "" {
		fmt.Fprintln(os.Stderr, "Error: --config is required")
		flag.Usage()
		os.Exit(1)
	}

	cfg, err := config.Load(*configPath, BuildMode)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading config: %v\n", err)
		os.Exit(1)
	}

	logger := log.NewLogger(cfg.Platform.LogLevel, BuildMode)
	defer logger.Sync()

	ctx, cancel := setupSignalHandling()
	defer cancel()

	code := Run(ctx, logger, cfg)
	os.Exit(code)
}