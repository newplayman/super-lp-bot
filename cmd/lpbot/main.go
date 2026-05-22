// Package main provides the main entry point for lpbot.
// It supports three build modes: dryrun, shadow, and live.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"flag"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
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

const (
	Version                  = "0.4.0"
	shadowCandidateLimit     = 10
	shadowOpenScoreThreshold = 60.0
	canaryMaxOrderUSD        = 5.0
)

var (
	BuildMode   = "dev"
	BuildCommit = "local"
	BuildDate   = ""
)

// App holds all initialized components.
type App struct {
	logger     *zap.Logger
	config     *config.Config
	liveGate   *liveSafetyGate
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

type liveSafetyGate struct {
	buildMode                  string
	enabled                    bool
	canary                     bool
	killSwitch                 bool
	walletAddress              string
	allowedChains              map[string]struct{}
	allowedPools               map[string]struct{}
	maxOrderUSD                float64
	dailyLossLimitUSD          float64
	executionBackend           string
	executionBackendConfigured bool
	executionBackendWired      bool
	rpcPrimaryConfigured       bool
	okxAPIConfigured           bool
	okxProjectConfigured       bool
	walletBackend              string
	keystorePath               string
	keystorePresent            bool
	walletPassphraseSet        bool
	npmBaseAddress             string
	npmBaseConfigured          bool
	sizingPathReady            bool
}

func newLiveSafetyGate(buildMode string, cfg *config.Config) *liveSafetyGate {
	gate := &liveSafetyGate{
		buildMode:     buildMode,
		allowedChains: make(map[string]struct{}),
		allowedPools:  make(map[string]struct{}),
	}
	if cfg == nil {
		return gate
	}

	gate.enabled = cfg.Live.Enabled
	gate.canary = cfg.Live.Canary
	gate.killSwitch = cfg.Live.KillSwitch
	gate.walletAddress = strings.TrimSpace(cfg.Live.WalletAddress)
	gate.maxOrderUSD = cfg.Live.MaxOrderUSD
	gate.dailyLossLimitUSD = cfg.Live.DailyLossLimitUSD
	gate.executionBackend = normalizeExecutionBackend(cfg.Execution.Backend)
	gate.rpcPrimaryConfigured = strings.TrimSpace(cfg.Chains.Base.RPCPrimary) != "" || rpc.ResolveQuickNodeAPIKey() != ""
	gate.okxAPIConfigured = strings.TrimSpace(cfg.Execution.OKXAPIKey) != "" &&
		strings.TrimSpace(cfg.Execution.OKXAPISecret) != "" &&
		strings.TrimSpace(cfg.Execution.OKXPassphrase) != ""
	gate.okxProjectConfigured = strings.TrimSpace(cfg.Execution.OKXProjectID) != ""
	gate.walletBackend = strings.ToLower(strings.TrimSpace(cfg.Wallet.Backend))
	gate.keystorePath = strings.TrimSpace(cfg.Wallet.KeystorePath)
	gate.keystorePresent = fileExists(gate.keystorePath)
	gate.walletPassphraseSet = strings.TrimSpace(cfg.Wallet.Passphrase) != ""
	gate.npmBaseAddress = strings.TrimSpace(cfg.Execution.NPMBaseAddress)
	gate.npmBaseConfigured = gate.npmBaseAddress != ""
	gate.sizingPathReady = nativeRPCLiveSizingSupported(cfg)
	gate.executionBackendConfigured = gate.backendConfigured()
	gate.executionBackendWired = liveExecutionPathAvailable(cfg)

	for _, chain := range cfg.Live.AllowedChains {
		normalized := strings.ToLower(strings.TrimSpace(chain))
		if normalized != "" {
			gate.allowedChains[normalized] = struct{}{}
		}
	}
	for _, poolID := range cfg.Live.AllowedPools {
		normalized := strings.ToLower(strings.TrimSpace(poolID))
		if normalized != "" {
			gate.allowedPools[normalized] = struct{}{}
		}
	}

	return gate
}

func normalizeExecutionBackend(value string) string {
	normalized := strings.ToLower(strings.TrimSpace(value))
	if normalized == "" {
		return "shadow"
	}
	return normalized
}

func fileExists(path string) bool {
	if strings.TrimSpace(path) == "" {
		return false
	}
	if _, err := os.Stat(filepath.Clean(path)); err == nil {
		return true
	}
	return false
}

func (g *liveSafetyGate) backendConfigured() bool {
	switch g.executionBackend {
	case "native-rpc":
		return g.rpcPrimaryConfigured
	case "okx-onchain":
		return g.okxAPIConfigured
	default:
		return false
	}
}

func (g *liveSafetyGate) isExecutionMode() bool {
	return strings.EqualFold(strings.TrimSpace(g.buildMode), "live")
}

func (g *liveSafetyGate) blockers() []string {
	if g == nil {
		return []string{"live gate not initialized"}
	}

	var blockers []string
	if !g.isExecutionMode() {
		blockers = append(blockers, fmt.Sprintf("build mode is %s", strings.TrimSpace(g.buildMode)))
	}
	if !g.enabled {
		blockers = append(blockers, "live.enabled=false")
	}
	if g.killSwitch {
		blockers = append(blockers, "live.kill_switch=true")
	}
	if g.walletAddress == "" {
		blockers = append(blockers, "live.wallet_address is empty")
	}
	if len(g.allowedChains) == 0 {
		blockers = append(blockers, "live.allowed_chains is empty")
	}
	if len(g.allowedPools) == 0 {
		blockers = append(blockers, "live.allowed_pools is empty")
	}
	if g.maxOrderUSD <= 0 {
		blockers = append(blockers, "live.max_order_usd must be > 0")
	}
	if g.canary && g.maxOrderUSD > canaryMaxOrderUSD {
		blockers = append(blockers, fmt.Sprintf("canary max_order_usd %.2f exceeds hard cap %.2f", g.maxOrderUSD, canaryMaxOrderUSD))
	}
	if g.dailyLossLimitUSD <= 0 {
		blockers = append(blockers, "live.daily_loss_limit_usd must be > 0")
	}
	if g.walletBackend == "keystore" {
		if g.keystorePath == "" {
			blockers = append(blockers, "wallet.keystore_path is empty")
		} else if !g.keystorePresent {
			blockers = append(blockers, "wallet.keystore_path does not exist on disk")
		}
		if !g.walletPassphraseSet {
			blockers = append(blockers, "wallet.passphrase is empty")
		}
	}
	if !g.npmBaseConfigured {
		blockers = append(blockers, "execution.npm_base_address is empty")
	}
	if !g.sizingPathReady {
		blockers = append(blockers, "amount_usd to token amount sizing path is not implemented")
	}
	if !g.executionBackendConfigured {
		switch g.executionBackend {
		case "native-rpc":
			blockers = append(blockers, "execution backend native-rpc requires chains.base.rpc_primary or QUICKNODE_API_KEY")
		case "okx-onchain":
			blockers = append(blockers, "execution backend okx-onchain requires OKX api key/secret/passphrase")
		default:
			blockers = append(blockers, fmt.Sprintf("execution.backend=%s is not configured", g.executionBackend))
		}
	}
	if !g.executionBackendWired {
		blockers = append(blockers, "executor is still shadow-only; live broadcaster is not wired in cmd/lpbot")
	}
	sort.Strings(blockers)
	return blockers
}

func (g *liveSafetyGate) readiness() dashboardLiveReadiness {
	if g == nil {
		return dashboardLiveReadiness{
			BuildMode: "unknown",
			Blockers:  []string{"live gate not initialized"},
		}
	}

	allowedChains := make([]string, 0, len(g.allowedChains))
	for chain := range g.allowedChains {
		allowedChains = append(allowedChains, chain)
	}
	sort.Strings(allowedChains)
	blockers := g.blockers()

	return dashboardLiveReadiness{
		BuildMode:             g.buildMode,
		LiveEnabled:           g.enabled,
		Canary:                g.canary,
		KillSwitch:            g.killSwitch,
		WalletAddress:         maskAddress(g.walletAddress),
		AllowedChains:         allowedChains,
		AllowedPoolsCount:     len(g.allowedPools),
		MaxOrderUSD:           g.maxOrderUSD,
		DailyLossLimitUSD:     g.dailyLossLimitUSD,
		ExecutionBackend:      g.executionBackend,
		ExecutionConfigured:   g.executionBackendConfigured,
		ExecutionBackendWired: g.executionBackendWired,
		RPCPrimaryConfigured:  g.rpcPrimaryConfigured,
		OKXAPIConfigured:      g.okxAPIConfigured,
		OKXProjectConfigured:  g.okxProjectConfigured,
		WalletBackend:         g.walletBackend,
		KeystorePath:          g.keystorePath,
		KeystorePresent:       g.keystorePresent,
		WalletPassphraseSet:   g.walletPassphraseSet,
		NPMBaseAddress:        g.npmBaseAddress,
		NPMBaseConfigured:     g.npmBaseConfigured,
		SizingPathReady:       g.sizingPathReady,
		Ready:                 len(blockers) == 0,
		Blockers:              blockers,
	}
}

func (g *liveSafetyGate) checkOpen(pool domain.Pool, amountUSD domain.Decimal) error {
	if g == nil || !g.isExecutionMode() {
		return nil
	}

	if blockers := g.blockers(); len(blockers) > 0 {
		return fmt.Errorf("live gate blocked: %s", strings.Join(blockers, "; "))
	}

	chain := strings.ToLower(strings.TrimSpace(string(pool.Chain)))
	if _, ok := g.allowedChains[chain]; !ok {
		return fmt.Errorf("live gate blocked: chain %s not in allowed_chains", pool.Chain)
	}

	poolID := strings.ToLower(strings.TrimSpace(pool.ID))
	if _, ok := g.allowedPools[poolID]; !ok {
		return fmt.Errorf("live gate blocked: pool %s not in allowed_pools", pool.ID)
	}

	maxOrder := domain.NewDecimalFromFloat(g.maxOrderUSD)
	if g.canary && g.maxOrderUSD > canaryMaxOrderUSD {
		maxOrder = domain.NewDecimalFromFloat(canaryMaxOrderUSD)
	}
	if amountUSD.GreaterThan(maxOrder) {
		return fmt.Errorf("live gate blocked: amount %s exceeds max_order_usd %s", amountUSD.String(), maxOrder.String())
	}

	return nil
}

func maskAddress(value string) string {
	trimmed := strings.TrimSpace(value)
	if len(trimmed) <= 12 {
		return trimmed
	}
	return trimmed[:6] + "..." + trimmed[len(trimmed)-4:]
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

	app := &App{logger: logger, config: cfg, liveGate: newLiveSafetyGate(BuildMode, cfg)}
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
	quickNodeHTTP := &http.Client{Timeout: 5 * time.Second}
	quickNodeAPIKey := rpc.ResolveQuickNodeAPIKey()
	var quickNodeDiscovered []rpc.QuickNodeEndpoint
	if quickNodeAPIKey != "" {
		discovered, err := rpc.DiscoverQuickNodeEndpoints(ctx, quickNodeAPIKey, quickNodeHTTP)
		if err != nil {
			app.logger.Warn("QuickNode endpoint discovery skipped", zap.Error(err))
		} else {
			quickNodeDiscovered = discovered
			baseQuickNode := rpc.PickQuickNodeHTTPEndpoints(discovered, "base")
			baseEndpoints = append(baseEndpoints, baseQuickNode...)
			if app.config.Chains.Base.WS == "" {
				if ws := rpc.PickQuickNodeWSURL(discovered, "base"); ws != "" {
					app.config.Chains.Base.WS = ws
				}
			}
			app.logger.Info("QuickNode endpoint discovery completed",
				zap.Int("discovered", len(discovered)),
				zap.Int("base_http", len(baseQuickNode)))
		}
	}
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

	solanaEndpoints := make([]string, 0, 2)
	if primary := strings.TrimSpace(app.config.Chains.Solana.RPCPrimary); primary != "" {
		solanaEndpoints = append(solanaEndpoints, primary)
	}
	solanaEndpoints = append(solanaEndpoints, rpc.PickQuickNodeHTTPEndpoints(quickNodeDiscovered, "solana")...)
	if len(solanaEndpoints) > 0 {
		provider, err := rpc.NewRoundRobinProvider(rpc.Config{
			ChainID:   domain.ChainSolana,
			Endpoints: solanaEndpoints,
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

	if err := app.ensureShadowDecisionTraceTable(ctx); err != nil {
		return fmt.Errorf("failed to initialize decision trace schema: %w", err)
	}
	if err := app.ensureShadowPositionMarksTable(ctx); err != nil {
		return fmt.Errorf("failed to initialize position mark schema: %w", err)
	}
	if err := app.ensureShadowExitDecisionsTable(ctx); err != nil {
		return fmt.Errorf("failed to initialize exit decision schema: %w", err)
	}
	if err := app.ensureShadowExitActionsTable(ctx); err != nil {
		return fmt.Errorf("failed to initialize exit action schema: %w", err)
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
	mux.HandleFunc("/metrics", app.dashboardAuth(metrics.Handler))
	app.registerDashboardRoutes(mux)

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
		store:          app.store,
		liveGate:       app.liveGate,
		provider:       app.rpc["base"],
		walletAddress:  parseAddressOrZero(strings.TrimSpace(app.config.Live.WalletAddress)),
		npmBaseAddress: strings.TrimSpace(app.config.Execution.NPMBaseAddress),
	}
	if app.logger != nil {
		app.logger.Info("ApproveTracker wired")
	}

	// Create OrderManager (placeholder - wired in execution module)
	orderManager := &orderManagerAdapter{
		riskGate: riskGate,
		store:    app.store,
		liveGate: app.liveGate,
		provider: app.rpc["base"],
		walletAddress: parseAddressOrZero(
			strings.TrimSpace(app.config.Live.WalletAddress),
		),
		npmBaseAddress: strings.TrimSpace(app.config.Execution.NPMBaseAddress),
	}
	if err := configureLiveExecution(ctx, app, orderManager); err != nil {
		return err
	}
	approveTracker.wallet = orderManager.wallet
	approveTracker.broadcaster = orderManager.broadcaster
	if app.logger != nil {
		app.logger.Info("OrderManager wired")
	}
	if app.logger != nil && app.liveGate != nil {
		readiness := app.liveGate.readiness()
		if readiness.Ready {
			app.logger.Info("live safety gate ready",
				zap.Bool("canary", readiness.Canary),
				zap.Float64("max_order_usd", readiness.MaxOrderUSD),
				zap.Float64("daily_loss_limit_usd", readiness.DailyLossLimitUSD))
		} else {
			app.logger.Warn("live safety gate not ready",
				zap.Bool("canary", readiness.Canary),
				zap.Strings("blockers", readiness.Blockers))
		}
	}

	// Create Simulator (placeholder - from existing implementation)
	simulator := &rpcSimulatorAdapter{
		provider: app.rpc["base"],
	}
	if app.logger != nil {
		app.logger.Info("RPC simulator wired")
	}

	// Create Metrics adapter with all required methods
	metrics := &metricsAdapter{}
	if app.logger != nil {
		app.logger.Info("Metrics wired")
	}

	// Create and configure the main loop
	app.mainLoop = loop.NewMainLoop(loop.MainLoopConfig{
		TickInterval:      1 * time.Minute,
		Broadcaster:       orderManager.broadcaster,
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

// startWorkers starts background workers for runtime services and strategy.
func (app *App) startWorkers(ctx context.Context) {
	if app.redis != nil {
		app.wg.Add(1)
		go func() {
			defer app.wg.Done()
			app.redis.Run(ctx)
		}()
	}

	// Strategy evaluation worker owns scan -> score -> shadow evaluation.
	app.wg.Add(1)
	go func() {
		defer app.wg.Done()
		app.runStrategyLoop(ctx)
	}()

	app.logger.Info("workers started",
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
			app.markShadowPositions(ctx)
		}
	}
}

// evaluateStrategies evaluates pools using the wired main loop.
// This function now delegates to the main loop which applies all risk gates,
// allocation checks, simulations, and approvals before any order is submitted.
func (app *App) evaluateStrategies(ctx context.Context) {
	if app.mainLoop == nil || app.scanner == nil {
		return
	}

	metrics.RecordLoopHeartbeat()

	scoredPools, err := app.scanner.ScanOnce(ctx)
	if err != nil {
		app.logger.Error("shadow scan failed", zap.Error(err))
		return
	}
	if len(scoredPools) == 0 {
		app.logger.Info("shadow scan completed with no candidates")
		return
	}

	pools := make([]domain.Pool, 0, len(scoredPools))
	scores := make(map[string]domain.Score, len(scoredPools))
	for _, scored := range scoredPools {
		pools = append(pools, scored.Pool)
		scores[scored.Pool.Key()] = scored.Score
		if app.store != nil {
			if err := app.store.PoolRepo().UpsertPool(ctx, ports.PoolWithScore{
				Pool:  scored.Pool,
				Score: scored.Score,
			}); err != nil {
				app.logger.Warn("shadow pool upsert failed",
					zap.String("pool", scored.Pool.Key()),
					zap.Error(err))
			}
		}
	}

	candidates := selectShadowCandidatesByScore(scoredPools, shadowCandidateLimit)

	tickTime := time.Now().Unix()
	candidateRanks := make(map[string]int, len(candidates))
	for idx, pool := range candidates {
		candidateRanks[pool.Key()] = idx + 1
	}

	evaluated := 0
	opened := 0
	traces := make([]shadowDecisionTraceRecord, 0, len(scoredPools))
	for _, scored := range scoredPools {
		pool := scored.Pool
		score := scores[pool.Key()]
		trace := app.buildDecisionTraceRecord(pool, score, tickTime)
		rank, selected := candidateRanks[pool.Key()]
		if !selected {
			trace.SelectionReason = fmt.Sprintf("not ranked in top %d candidates for this tick", len(candidates))
			traces = append(traces, trace)
			continue
		}

		trace.Selected = true
		trace.SelectedRank = rank
		trace.SelectionReason = fmt.Sprintf("ranked #%d of %d selected candidates", rank, len(candidates))
		intent, err := app.strategy.EvaluatePool(ctx, pool, score)
		if err != nil {
			trace.PipelineStage = "strategy_error"
			trace.PipelineReason = err.Error()
			trace.FinalAction = "skip"
			traces = append(traces, trace)
			app.logger.Warn("shadow strategy evaluation failed",
				zap.String("pool", pool.Key()),
				zap.Error(err))
			continue
		}
		if intent == nil {
			trace.IntentReason = fmt.Sprintf("score threshold not met: total %.1f < %.0f", score.ComputeTotal(), shadowOpenScoreThreshold)
			traces = append(traces, trace)
			continue
		}

		trace.IntentOpen = true
		trace.IntentReason = intent.Reason
		trace.TraceID = shadowID("trace", fmt.Sprintf("%s:%d:%d", pool.Key(), rank, tickTime), tickTime)
		evaluated++
		pipeline := app.evaluateShadowPipeline(ctx, pool)
		trace.ChainStage = pipeline.ChainStage
		trace.ChainReason = pipeline.ChainReason
		trace.PipelineStage = pipeline.Stage
		trace.PipelineOK = pipeline.OK
		trace.PipelineReason = pipeline.Reason
		trace.FinalAction = pipeline.Action
		trace.PositionID = pipeline.PositionID
		trace.TxHash = pipeline.TxHash
		traces = append(traces, trace)
		if pipeline.OK {
			opened++
			continue
		}

		app.logger.Warn("shadow pipeline evaluation failed",
			zap.String("pool", pool.Key()),
			zap.String("stage", pipeline.Stage),
			zap.String("reason", pipeline.Reason))
	}

	if err := app.persistShadowDecisionTraces(ctx, traces); err != nil {
		app.logger.Warn("shadow decision trace persist failed", zap.Error(err))
	}

	app.logger.Info("shadow strategy tick completed",
		zap.Int("scanned", len(scoredPools)),
		zap.Int("candidates", len(candidates)),
		zap.Int("evaluated", evaluated),
		zap.Int("shadow_orders", opened))
	metrics.RecordShadowTick(len(scoredPools), len(candidates), evaluated, opened)
}

func selectShadowCandidatesByScore(scoredPools []scanner.ScoredPool, limit int) []domain.Pool {
	if limit <= 0 {
		limit = shadowCandidateLimit
	}
	ranked := append([]scanner.ScoredPool(nil), scoredPools...)
	sort.SliceStable(ranked, func(i, j int) bool {
		left := ranked[i].Score.Total
		if left == 0 {
			left = ranked[i].Score.ComputeTotal()
		}
		right := ranked[j].Score.Total
		if right == 0 {
			right = ranked[j].Score.ComputeTotal()
		}
		return left > right
	})

	candidates := make([]domain.Pool, 0, minInt(limit, len(ranked)))
	for i := 0; i < len(ranked) && len(candidates) < limit; i++ {
		score := ranked[i].Score.Total
		if score == 0 {
			score = ranked[i].Score.ComputeTotal()
		}
		if score < shadowOpenScoreThreshold {
			continue
		}
		candidates = append(candidates, ranked[i].Pool)
	}
	return candidates
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
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

func (m *metricsAdapter) IncRiskBlock()                  { metrics.IncRiskBlock() }
func (m *metricsAdapter) IncAllocBlock()                 { metrics.IncAllocBlock() }
func (m *metricsAdapter) IncSimulateFail()               { metrics.IncSimulateFail() }
func (m *metricsAdapter) IncApproveFail()                { metrics.IncApproveFail() }
func (m *metricsAdapter) IncTxFailed()                   { metrics.IncTxFailed("", "", "shadow_pipeline") }
func (m *metricsAdapter) IncLoopHeartbeat()              { metrics.RecordLoopHeartbeat() }
func (m *metricsAdapter) SetPositionsOpen(n int64)       {}
func (m *metricsAdapter) SetPositionsClosed(n int64)     {}
func (m *metricsAdapter) SetPnLDaily(pnl domain.Decimal) {}

type approveTrackerAdapter struct {
	store          ports.Store
	liveGate       *liveSafetyGate
	provider       *rpc.RoundRobinProvider
	wallet         ports.Wallet
	broadcaster    ports.Broadcaster
	walletAddress  domain.Address
	npmBaseAddress string
}

func (a *approveTrackerAdapter) HasAllowance(pool domain.Pool) bool {
	if a == nil || a.liveGate == nil || !a.liveGate.isExecutionMode() {
		return true
	}
	if pool.Chain != domain.ChainBase || a.provider == nil || a.walletAddress.IsZero() {
		return false
	}
	spender := parseAddressOrZero(strings.TrimSpace(a.npmBaseAddress))
	if spender.IsZero() {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	for _, token := range []domain.Address{pool.Token0, pool.Token1} {
		allowance, err := dashboardERC20Allowance(ctx, a.provider, token.String(), a.walletAddress, spender)
		if err != nil || allowance.Sign() <= 0 {
			return false
		}
	}
	return true
}

func (a *approveTrackerAdapter) EnsureApproval(ctx context.Context, pool domain.Pool) error {
	if a == nil || a.liveGate == nil || !a.liveGate.isExecutionMode() {
		return nil
	}
	if a.HasAllowance(pool) {
		return nil
	}
	if a.wallet == nil || a.broadcaster == nil {
		return fmt.Errorf("live approval components not configured; refusing to approve pool %s", pool.ID)
	}
	amountUSD := domain.NewDecimalFromFloat(a.liveGate.maxOrderUSD)
	if a.liveGate.canary && a.liveGate.maxOrderUSD > canaryMaxOrderUSD {
		amountUSD = domain.NewDecimalFromFloat(canaryMaxOrderUSD)
	}
	if err := a.liveGate.checkOpen(pool, amountUSD); err != nil {
		return err
	}
	spender := parseAddressOrZero(strings.TrimSpace(a.npmBaseAddress))
	if spender.IsZero() {
		return fmt.Errorf("npm spender address not configured")
	}
	intent, err := buildBaseOpenIntent(ctx, a.provider, a.walletAddress, pool, amountUSD, shadowID("approve", pool.Key(), time.Now().Unix()), time.Now())
	if err != nil {
		return fmt.Errorf("build exact approval sizing: %w", err)
	}
	needed := []struct {
		token  domain.Address
		amount *big.Int
		name   string
	}{
		{token: pool.Token0, amount: intent.Amount0.BigInt(), name: "token0"},
		{token: pool.Token1, amount: intent.Amount1.BigInt(), name: "token1"},
	}
	for _, item := range needed {
		if item.amount.Sign() <= 0 {
			continue
		}
		balance, err := dashboardERC20Balance(ctx, a.provider, item.token.String(), a.walletAddress)
		if err != nil {
			return fmt.Errorf("check %s balance before approval: %w", item.name, err)
		}
		if balance.Cmp(item.amount) < 0 && strings.EqualFold(item.token.String(), baseWETHAddress) {
			if err := a.wrapWETH(ctx, pool, new(big.Int).Sub(item.amount, balance)); err != nil {
				return err
			}
			balance, err = dashboardERC20Balance(ctx, a.provider, item.token.String(), a.walletAddress)
			if err != nil {
				return fmt.Errorf("recheck %s balance after wrap: %w", item.name, err)
			}
		}
		if balance.Cmp(item.amount) < 0 {
			return fmt.Errorf("insufficient %s balance for exact approval: need %s raw, have %s raw", item.name, item.amount.String(), balance.String())
		}
		allowance, err := dashboardERC20Allowance(ctx, a.provider, item.token.String(), a.walletAddress, spender)
		if err != nil {
			return fmt.Errorf("check %s allowance: %w", item.name, err)
		}
		if allowance.Cmp(item.amount) >= 0 {
			continue
		}
		tx, err := a.wallet.ApproveExact(ctx, item.token, spender, item.amount)
		if err != nil {
			return fmt.Errorf("build %s exact approval: %w", item.name, err)
		}
		tx.ID = shadowID("approve-tx", fmt.Sprintf("%s:%s", pool.Key(), item.token.String()), time.Now().Unix())
		tx.Deadline = time.Now().Add(5 * time.Minute).Unix()
		tx.MinOut = domain.NewDecimalFromInt(1)
		if err := a.preflightApprovalTx(ctx, tx); err != nil {
			return fmt.Errorf("preflight %s approval: %w", item.name, err)
		}
		signed, err := a.wallet.Sign(ctx, tx)
		if err != nil {
			return fmt.Errorf("sign %s approval: %w", item.name, err)
		}
		signed.ID = tx.ID
		signed.Status = domain.TxBuilt
		if a.store != nil {
			_ = a.store.TxRepo().UpsertTx(ctx, signed)
		}
		if err := a.broadcaster.Send(ctx, signed); err != nil {
			signed.Status = domain.TxFailed
			if a.store != nil {
				_ = a.store.TxRepo().UpsertTx(ctx, signed)
			}
			return fmt.Errorf("broadcast %s approval: %w", item.name, err)
		}
		signed.Status = domain.TxBroadcast
		if a.store != nil {
			_ = a.store.TxRepo().UpsertTx(ctx, signed)
		}
	}
	return nil
}

func (a *approveTrackerAdapter) wrapWETH(ctx context.Context, pool domain.Pool, amountWei *big.Int) error {
	if amountWei == nil || amountWei.Sign() <= 0 {
		return nil
	}
	ethBalance, err := a.provider.BalanceAt(ctx, a.walletAddress, nil)
	if err != nil {
		return fmt.Errorf("check ETH balance before WETH wrap: %w", err)
	}
	gasReserveWei := new(big.Int).Mul(big.NewInt(5), big.NewInt(100000000000000))
	if ethBalance.Cmp(new(big.Int).Add(amountWei, gasReserveWei)) < 0 {
		return fmt.Errorf("insufficient ETH to wrap WETH and keep gas reserve: need %s raw plus reserve %s raw, have %s raw", amountWei.String(), gasReserveWei.String(), ethBalance.String())
	}
	tx := domain.UnsignedTx{
		ID:       shadowID("wrap-weth", pool.Key(), time.Now().Unix()),
		Chain:    domain.ChainBase,
		From:     a.walletAddress,
		To:       domain.MustParseAddress(baseWETHAddress),
		Data:     common.FromHex("0xd0e30db0"),
		Value:    domain.MustDecimal(amountWei.String()),
		Deadline: time.Now().Add(5 * time.Minute).Unix(),
		MinOut:   domain.NewDecimalFromInt(1),
	}
	if err := a.preflightApprovalTx(ctx, tx); err != nil {
		return fmt.Errorf("preflight WETH wrap: %w", err)
	}
	signed, err := a.wallet.Sign(ctx, tx)
	if err != nil {
		return fmt.Errorf("sign WETH wrap: %w", err)
	}
	signed.ID = tx.ID
	signed.Status = domain.TxBuilt
	if a.store != nil {
		_ = a.store.TxRepo().UpsertTx(ctx, signed)
	}
	if err := a.broadcaster.Send(ctx, signed); err != nil {
		signed.Status = domain.TxFailed
		if a.store != nil {
			_ = a.store.TxRepo().UpsertTx(ctx, signed)
		}
		return fmt.Errorf("broadcast WETH wrap: %w", err)
	}
	signed.Status = domain.TxBroadcast
	if a.store != nil {
		_ = a.store.TxRepo().UpsertTx(ctx, signed)
	}
	return nil
}

func (a *approveTrackerAdapter) preflightApprovalTx(ctx context.Context, tx domain.UnsignedTx) error {
	if a == nil || a.provider == nil {
		return fmt.Errorf("base rpc provider not configured")
	}
	to := common.HexToAddress(tx.To.String())
	_, err := a.provider.CallContract(ctx, ethereum.CallMsg{
		From:  common.HexToAddress(tx.From.String()),
		To:    &to,
		Value: tx.Value.BigInt(),
		Data:  tx.Data,
	}, nil)
	return err
}

type orderManagerAdapter struct {
	broadcaster    ports.Broadcaster
	riskGate       *risk.RiskGate
	store          ports.Store
	liveGate       *liveSafetyGate
	provider       *rpc.RoundRobinProvider
	wallet         ports.Wallet
	walletAddress  domain.Address
	npmBaseAddress string
}

func (o *orderManagerAdapter) Open(ctx context.Context, pool domain.Pool, amountUSD domain.Decimal) (loop.ExecutionResult, error) {
	if o.store == nil {
		return loop.ExecutionResult{Success: false, Error: "store not configured"}, nil
	}
	if o.liveGate != nil {
		if err := o.liveGate.checkOpen(pool, amountUSD); err != nil {
			return loop.ExecutionResult{Success: false, Error: err.Error()}, nil
		}
	}

	for _, status := range []domain.PositionStatus{domain.StatusIntended, domain.StatusOpening, domain.StatusOpen} {
		existing, err := o.store.PositionRepo().FindByPoolAndStatus(ctx, pool.ID, status)
		if err != nil {
			return loop.ExecutionResult{}, err
		}
		if len(existing) > 0 {
			return loop.ExecutionResult{
				Success:     true,
				PositionID:  existing[0].ID,
				FinalStatus: existing[0].Status,
			}, nil
		}
	}

	now := time.Now().Unix()
	positionID := shadowID("pos", pool.Key(), now)
	position := &domain.Position{
		ID:        positionID,
		PoolID:    pool.ID,
		Chain:     pool.Chain,
		Status:    domain.StatusIntended,
		Tier:      pool.Tier_,
		AmountUSD: amountUSD,
		TickLower: int64(pool.Tick) - 100,
		TickUpper: int64(pool.Tick) + 100,
		OpenedAt:  now,
	}
	if position.TickLower == -100 && position.TickUpper == 100 {
		position.TickLower = -500
		position.TickUpper = 500
	}

	if err := o.store.PositionRepo().Save(ctx, position); err != nil {
		return loop.ExecutionResult{}, err
	}

	txHash := shadowID("tx", positionID, now)
	tx, err := o.buildPreparedMintTx(ctx, pool, amountUSD, positionID, time.Unix(now, 0))
	if err != nil {
		if o.liveGate != nil && o.liveGate.isExecutionMode() {
			return loop.ExecutionResult{Success: false, Error: err.Error()}, nil
		}

		tx = domain.SignedTx{
			UnsignedTx: domain.UnsignedTx{
				ID:       txHash,
				Chain:    pool.Chain,
				From:     zeroEVMAddress(),
				To:       parseAddressOrZero(pool.ID),
				Value:    domain.ZeroDecimal(),
				Deadline: now + 300,
				MinOut:   domain.ZeroDecimal(),
			},
			Hash:   txHash,
			Status: domain.TxBuilt,
		}
	}

	if o.liveGate != nil && o.liveGate.isExecutionMode() {
		if o.wallet == nil || o.broadcaster == nil {
			return loop.ExecutionResult{Success: false, Error: "live execution components not configured"}, nil
		}
		if err := o.preflightPreparedTx(ctx, tx.UnsignedTx); err != nil {
			return loop.ExecutionResult{Success: false, Error: fmt.Sprintf("live preflight failed: %v", err)}, nil
		}
		signed, err := o.wallet.Sign(ctx, tx.UnsignedTx)
		if err != nil {
			return loop.ExecutionResult{Success: false, Error: fmt.Sprintf("wallet sign failed: %v", err)}, nil
		}
		signed.ID = tx.ID
		signed.Status = domain.TxBuilt
		if err := o.broadcaster.Send(ctx, signed); err != nil {
			signed.Status = domain.TxFailed
			_ = o.store.TxRepo().UpsertTx(ctx, signed)
			return loop.ExecutionResult{Success: false, Error: fmt.Sprintf("broadcast failed: %v", err)}, nil
		}
		signed.Status = domain.TxBroadcast
		tx = signed
		txHash = signed.Hash
	}
	if err := o.store.TxRepo().UpsertTx(ctx, tx); err != nil {
		return loop.ExecutionResult{}, err
	}

	return loop.ExecutionResult{
		TxHash:      txHash,
		Success:     true,
		PositionID:  positionID,
		FinalStatus: domain.StatusIntended,
	}, nil
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

type rpcSimulatorAdapter struct {
	provider *rpc.RoundRobinProvider
}

func (s *rpcSimulatorAdapter) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	if s == nil || s.provider == nil {
		return &domain.SimulationResult{Success: false, Error: "rpc provider not configured"}, nil
	}

	c := context.Background()
	if typed, ok := ctx.(context.Context); ok {
		c = typed
	}

	header, err := s.provider.HeaderByNumber(c, nil)
	if err != nil {
		return &domain.SimulationResult{Success: false, Error: err.Error(), BlockRef: blockRef}, nil
	}

	result := &domain.SimulationResult{
		Success: true,
		BlockRef: domain.BlockRef{
			Chain:    s.provider.ChainID(),
			Number:   header.Number.Uint64(),
			Hash:     header.Hash().Hex(),
			TimeUnix: int64(header.Time),
		},
	}

	if !tx.To.IsZero() || len(tx.Data) > 0 {
		msg := ethereum.CallMsg{
			From:  common.HexToAddress(tx.From.String()),
			To:    addressPtr(tx.To),
			Value: decimalToBigInt(tx.Value),
			Data:  tx.Data,
		}
		gas, err := s.provider.EstimateGas(c, msg)
		if err != nil {
			return &domain.SimulationResult{Success: false, Error: err.Error(), BlockRef: result.BlockRef}, nil
		}
		result.GasUsed = gas
	}

	gasPrice, err := s.provider.SuggestGasPrice(c)
	if err == nil {
		result.GasPrice = gasPrice
	}

	return result, nil
}

func (s *rpcSimulatorAdapter) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	results := make([]domain.SimulationResult, 0, len(txs))
	for _, tx := range txs {
		result, err := s.Simulate(ctx, tx, blockRef)
		if err != nil {
			return results, err
		}
		results = append(results, *result)
		if !result.Success {
			break
		}
	}
	return results, nil
}

func shadowID(prefix string, key string, ts int64) string {
	sum := sha256.Sum256([]byte(fmt.Sprintf("%s:%s:%d", prefix, key, ts)))
	return fmt.Sprintf("shadow-%s-%s", prefix, hex.EncodeToString(sum[:])[:24])
}

func zeroEVMAddress() domain.Address {
	return domain.MustParseAddress("0x0000000000000000000000000000000000000000")
}

func parseAddressOrZero(value string) domain.Address {
	addr, err := domain.ParseAddress(value)
	if err != nil {
		return zeroEVMAddress()
	}
	return addr
}

func addressPtr(addr domain.Address) *common.Address {
	ethAddr := common.HexToAddress(addr.String())
	return &ethAddr
}

func decimalToBigInt(value domain.Decimal) *big.Int {
	if value.IsZero() {
		return big.NewInt(0)
	}
	return value.BigInt()
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
	canaryPreflight := flag.Bool("canary-preflight", false, "Run a single Base canary preflight without signing or broadcasting")
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

	if *canaryPreflight {
		if BuildMode != "live" {
			fmt.Fprintln(os.Stderr, "Error: --canary-preflight requires a live build")
			os.Exit(1)
		}
		if err := runCanaryPreflight(ctx, cfg); err != nil {
			fmt.Fprintf(os.Stderr, "Canary preflight failed: %v\n", err)
			os.Exit(1)
		}
		return
	}

	code := Run(ctx, logger, cfg)
	os.Exit(code)
}
