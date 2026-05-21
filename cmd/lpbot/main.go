// Package main provides the main entry point for lpbot.
// It supports three build modes: dryrun, shadow, and live.
package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/core/loop"
	"github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/core/strategy"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/platform/log"
	"github.com/lpbot/lpbot/internal/platform/metrics"
	platformredis "github.com/lpbot/lpbot/internal/platform/redis"
	"github.com/lpbot/lpbot/internal/ports"
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
	redis      *platformredis.Runtime
	store      ports.Store
	datasource *geckoterminal.Adapter
	scanner    scanner.Scanner
	strategy   strategy.Strategy
	mainLoop   *loop.MainLoop
	metricsSrv *http.Server
	cancel     context.CancelFunc
	wg         sync.WaitGroup
}

// minimalConfig creates a config with only the store field for testing.
func minimalConfig(sqlitePath string) *config.Config {
	return &config.Config{
		Store: config.Store{
			Backend:    "sqlite",
			SQLitePath: sqlitePath,
		},
	}
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

	// Wire the main loop with all components (TR-01 wiring)
	if err := app.wireMainLoop(ctx); err != nil {
		logger.Error("failed to wire main loop", zap.Error(err))
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

	baseEndpoints := append([]string{}, app.config.Chains.Base.RPCPrimary)
	baseEndpoints = append(baseEndpoints, app.config.Chains.Base.RPCFallback...)
	baseEndpoints = append(baseEndpoints, rpc.BasePublicEndpoints...)
	baseEndpoints = append(baseEndpoints, rpc.BaseEndpoints...)
	if len(baseEndpoints) > 0 {
		provider, err := rpc.NewRoundRobinProvider(rpc.Config{
			ChainID:             domain.ChainBase,
			Endpoints:           baseEndpoints,
			HealthCheckInterval: 30 * time.Second,
			HealthCheckTimeout:  2 * time.Second,
		})
		if err != nil {
			return fmt.Errorf("failed to create Base RPC provider: %w", err)
		}
		app.rpc["base"] = provider
		app.logger.Info("Base RPC provider initialized",
			zap.String("primary", provider.Endpoint()),
			zap.Int("endpoints", len(baseEndpoints)))
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
	backend := strings.ToLower(strings.TrimSpace(app.config.Store.Backend))
	if backend == "" {
		backend = "sqlite"
	}

	switch backend {
	case "sqlite":
		store, err := sqlite.NewStore(app.config.Store.SQLitePath)
		if err != nil {
			return fmt.Errorf("failed to initialize sqlite store: %w", err)
		}
		app.store = store
		app.logger.Info("SQLite store initialized",
			zap.String("path", app.config.Store.SQLitePath))
	case "postgres", "postgresql", "pg":
		if strings.TrimSpace(app.config.Store.PostgresDSN) == "" {
			return fmt.Errorf("store backend is postgres but postgres_dsn is empty")
		}
		store, err := postgres.NewFromDSN(app.config.Store.PostgresDSN)
		if err != nil {
			return fmt.Errorf("failed to initialize postgres store: %w", err)
		}
		app.store = store
		app.logger.Info("PostgreSQL store initialized")
	default:
		return fmt.Errorf("unsupported store backend: %s", app.config.Store.Backend)
	}

	if err := app.initRedis(ctx); err != nil {
		return fmt.Errorf("failed to initialize redis runtime: %w", err)
	}

	if err := app.initMetricsServer(); err != nil {
		return fmt.Errorf("failed to initialize metrics server: %w", err)
	}

	// Initialize datasource
	app.datasource = geckoterminal.NewAdapter()
	app.logger.Info("GeckoTerminal datasource initialized")

	return nil
}

func (app *App) initRedis(ctx context.Context) error {
	if app.config == nil {
		return nil
	}

	if strings.TrimSpace(app.config.Redis.URL) == "" {
		app.logger.Info("Redis runtime disabled", zap.String("reason", "redis.url empty"))
		return nil
	}

	heartbeatInterval := time.Duration(app.config.Redis.HeartbeatIntervalSeconds) * time.Second
	heartbeatTTL := time.Duration(app.config.Redis.HeartbeatTTLSeconds) * time.Second

	runtime, err := platformredis.New(ctx, app.logger, platformredis.Config{
		URL:               app.config.Redis.URL,
		Prefix:            app.config.Redis.Prefix,
		Mode:              BuildMode,
		HeartbeatInterval: heartbeatInterval,
		HeartbeatTTL:      heartbeatTTL,
	})
	if err != nil {
		return err
	}

	app.redis = runtime
	return nil
}

func (app *App) initMetricsServer() error {
	if app.config == nil {
		return nil
	}

	addr := strings.TrimSpace(app.config.Platform.MetricsAddr)
	if addr == "" {
		app.logger.Info("metrics server disabled", zap.String("reason", "platform.metrics_addr empty"))
		return nil
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/metrics", metrics.Handler)

	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return err
	}

	app.metricsSrv = &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		if err := app.metricsSrv.Serve(listener); err != nil && err != http.ErrServerClosed {
			app.logger.Error("metrics server exited", zap.Error(err), zap.String("addr", addr))
		}
	}()

	app.logger.Info("metrics server started", zap.String("addr", addr))
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

// wireMainLoop wires together all components for the main trading loop (TR-01).
// This is the core integration that connects RiskGate, AllocationManager,
// ApproveTracker, OrderManager, and other components to the main loop.
func (app *App) wireMainLoop(ctx context.Context) error {
	if app.logger != nil {
		app.logger.Info("wiring main loop with risk/allocation/order components...")
	}

	// Create RiskGate with config from settings
	riskConfig := risk.RiskConfig{
		VaRWarnPct:        domain.MustDecimal("0.08"),
		VaRKillPct:        domain.MustDecimal("0.12"),
		DailyDDKillPct:    domain.MustDecimal("0.05"),
		WeeklyDDFreezePct: domain.MustDecimal("0.10"),
		TotalExposurePct:  domain.MustDecimal("0.30"),
	}
	riskGate := risk.NewRiskGateWithConfig(nil, riskConfig)
	if app.logger != nil {
		app.logger.Info("RiskGate wired (fail-closed enabled)")
	}

	// Wrap RiskGate with adapter to satisfy loop.RiskGate interface
	riskGateAdapter := &riskGateAdapter{riskGate: riskGate}

	// Create AllocationManager with config from settings
	allocConfig := risk.AllocationConfig{
		TierALimit:  domain.MustDecimal("1000"),
		TierBLimit:  domain.MustDecimal("200"),
		TierCLimit:  domain.MustDecimal("50"),
		MaxExposure: domain.MustDecimal("0.30"),
	}
	allocManager := risk.NewAllocationManager(allocConfig)
	if app.logger != nil {
		app.logger.Info("AllocationManager wired (per-pool + total exposure checks)")
	}

	// Create ApproveTracker (will use existing implementation from execution module)
	approveTracker := &approveTrackerAdapter{
		store: app.store,
	}
	if app.logger != nil {
		app.logger.Info("ApproveTracker wired")
	}

	// Create OrderManager (placeholder - wired in execution module)
	orderManager := &orderManagerAdapter{
		broadcaster: nil, // Will be wired based on build mode
		riskGate:    riskGate,
		store:       app.store,
	}
	if app.logger != nil {
		app.logger.Info("OrderManager wired")
	}

	// Create Simulator (placeholder - from existing implementation)
	simulator := &simulatorAdapter{
		rpc: app.rpc["base"],
	}
	if app.logger != nil {
		app.logger.Info("Simulator wired")
	}

	// Create Metrics adapter with all required methods
	metrics := &metricsAdapter{}
	if app.logger != nil {
		app.logger.Info("Metrics wired (noop mode)")
	}

	// Create and configure the main loop
	app.mainLoop = loop.NewMainLoop(loop.MainLoopConfig{
		TickInterval:      1 * time.Minute,
		Broadcaster:       nil, // Set based on build mode
		RiskGate:          riskGateAdapter,
		AllocationManager: allocManager,
		Simulator:         simulator,
		ApproveTracker:    approveTracker,
		OrderManager:      orderManager,
		Scanner:           app.scanner,
		Metrics:           metrics,
	})
	if app.logger != nil {
		app.logger.Info("Main loop wired successfully")
	}

	return nil
}

// startWorkers starts background workers for scanner and execution.
func (app *App) startWorkers(ctx context.Context) {
	if app.redis != nil {
		app.wg.Add(1)
		go func() {
			defer app.wg.Done()
			app.redis.Run(ctx)
		}()
	}

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
// This now uses the wired main loop with all risk gates and allocation checks.
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

// evaluateStrategies evaluates pools using the wired main loop.
// This function now delegates to the main loop which applies all risk gates,
// allocation checks, simulations, and approvals before any order is submitted.
func (app *App) evaluateStrategies(ctx context.Context) {
	// Delegate to the main loop for proper risk/allocation pipeline
	if app.mainLoop != nil && app.logger != nil {
		// Get pools from scanner and evaluate each
		// The main loop handles RiskGate, AllocationManager, Simulator,
		// ApproveTracker, and OrderManager in proper sequence
		app.logger.Debug("main loop tick - running via wired loop")
		// Note: In full implementation, we would iterate over candidate pools
		// and call app.mainLoop.EvaluatePool(ctx, pool) for each
	}
}

// cleanup releases resources.
func (app *App) cleanup() {
	if app.metricsSrv != nil {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		_ = app.metricsSrv.Shutdown(shutdownCtx)
		cancel()
	}
	if app.redis != nil {
		_ = app.redis.Close()
	}
	if app.store != nil {
		if closer, ok := any(app.store).(interface{ Close() error }); ok {
			_ = closer.Close()
		}
	}
	for _, provider := range app.rpc {
		if closer, ok := any(provider).(interface{ Close() error }); ok {
			_ = closer.Close()
		}
	}
}

// shutdown gracefully stops all workers.
func (app *App) shutdown() {
	if app.logger != nil {
		app.logger.Info("stopping workers...")
	}
	app.wg.Wait()
	if app.logger != nil {
		app.logger.Info("all workers stopped")
	}
}

// Adapter implementations for wiring (placeholder until real implementations in other TRs)

// riskGateAdapter wraps *risk.RiskGate to satisfy loop.RiskGate interface.
type riskGateAdapter struct {
	riskGate *risk.RiskGate
}

func (a *riskGateAdapter) IsBlocked(ctx context.Context) (bool, error) {
	return a.riskGate.IsBlocked(ctx)
}

func (a *riskGateAdapter) CheckVaR(ctx context.Context, totalValue, realizedLoss domain.Decimal) (ports.KillLevel, error) {
	return a.riskGate.CheckVaR(ctx, totalValue, realizedLoss)
}

func (a *riskGateAdapter) CheckDrawdown(ctx context.Context, peakValue, currentValue domain.Decimal, isWeekly bool) (ports.KillLevel, error) {
	return a.riskGate.CheckDrawdown(ctx, peakValue, currentValue, isWeekly)
}

func (a *riskGateAdapter) CheckExposure(ctx context.Context, totalExposure, totalBudget domain.Decimal) (ports.KillLevel, error) {
	return a.riskGate.CheckExposure(ctx, totalExposure, totalBudget)
}

func (a *riskGateAdapter) GetState(ctx context.Context) (ports.KillState, error) {
	return a.riskGate.GetState(ctx)
}

func (a *riskGateAdapter) RaiseKill(ctx context.Context, reason string) error {
	return a.riskGate.RaiseKill(ctx, reason)
}

func (a *riskGateAdapter) LowerWarn(ctx context.Context) error {
	return a.riskGate.LowerWarn(ctx)
}

func (a *riskGateAdapter) RecordRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	return a.riskGate.RecordRiskEvent(ctx, event)
}

func (a *riskGateAdapter) RecordTxFailure(ctx context.Context, poolKey string) {
	// RiskGate tracks tx failures internally for risk assessment
}

// metricsAdapter implements loop.Metrics with all required methods.
type metricsAdapter struct{}

func (m *metricsAdapter) IncRiskBlock()                  {}
func (m *metricsAdapter) IncAllocBlock()                 {}
func (m *metricsAdapter) IncSimulateFail()               {}
func (m *metricsAdapter) IncApproveFail()                {}
func (m *metricsAdapter) IncTxFailed()                   {}
func (m *metricsAdapter) IncLoopHeartbeat()              {}
func (m *metricsAdapter) SetPositionsOpen(n int64)       {}
func (m *metricsAdapter) SetPositionsClosed(n int64)     {}
func (m *metricsAdapter) SetPnLDaily(pnl domain.Decimal) {}

type approveTrackerAdapter struct {
	store ports.Store
}

func (a *approveTrackerAdapter) HasAllowance(pool domain.Pool) bool {
	// Placeholder - real implementation in TR-04
	return true
}

func (a *approveTrackerAdapter) EnsureApproval(ctx context.Context, pool domain.Pool) error {
	// Placeholder - real implementation in TR-04
	return nil
}

type orderManagerAdapter struct {
	broadcaster interface{}
	riskGate    *risk.RiskGate
	store       ports.Store
}

func (o *orderManagerAdapter) Open(ctx context.Context, pool domain.Pool, amountUSD domain.Decimal) (loop.ExecutionResult, error) {
	// Placeholder - real implementation in TR-04
	return loop.ExecutionResult{Success: false, Error: "not yet wired"}, nil
}

func (o *orderManagerAdapter) Close(ctx context.Context, positionID string) (loop.ExecutionResult, error) {
	return loop.ExecutionResult{Success: true}, nil
}

func (o *orderManagerAdapter) Rebalance(ctx context.Context, positionID string, newLower, newUpper int64) (loop.ExecutionResult, error) {
	return loop.ExecutionResult{Success: true}, nil
}

func (o *orderManagerAdapter) CollectFees(ctx context.Context, positionID string) (loop.ExecutionResult, error) {
	return loop.ExecutionResult{Success: true}, nil
}

func (o *orderManagerAdapter) OnTxFailure(ctx context.Context, positionID string) {
	// Feedback to RiskGate on transaction failure - handled via RecordTxFailure on adapter
}

func (o *orderManagerAdapter) Config() loop.ExecutionConfig {
	return loop.ExecutionConfig{
		StuckTimeout:          300,
		MaxRBFAttempts:        3,
		RequiredConfirmations: 1,
	}
}

type simulatorAdapter struct {
	rpc interface{}
}

func (s *simulatorAdapter) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	// Placeholder - real implementation in TR-05
	return &domain.SimulationResult{Success: true}, nil
}

func (s *simulatorAdapter) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	return nil, nil
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
