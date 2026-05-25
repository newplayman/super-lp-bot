// Package main provides the main entry point for lpbot.
// It supports three build modes: dryrun, shadow, and live.
package main

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"flag"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"net/url"
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
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/core/loop"
	"github.com/lpbot/lpbot/internal/core/risk"
	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/core/strategy"
	"github.com/lpbot/lpbot/internal/core/watchdog"
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
	canaryMaxOrderUSD        = 20.0
	manualCanaryOverrideEnv  = "LPBOT_MANUAL_CANARY_OVERRIDE"
	dashboardSnapshotTTL     = 15 * time.Second
)

var (
	BuildMode   = "dev"
	BuildCommit = "local"
	BuildDate   = ""
)

// App holds all initialized components.
type App struct {
	logger         *zap.Logger
	config         *config.Config
	liveGate       *liveSafetyGate
	rpc            map[string]*rpc.RoundRobinProvider
	redis          *platformredis.Runtime
	alerter        ports.Alerter
	store          ports.Store
	datasource     *geckoterminal.Adapter
	scanner        scanner.Scanner
	strategy       strategy.Strategy
	mainLoop       *loop.MainLoop
	watchdog       watchdog.Watchdog
	metricsSrv     *http.Server
	cancel         context.CancelFunc
	wg             sync.WaitGroup
	dashboardCache dashboardSnapshotCache
}

type dashboardSnapshotCache struct {
	mu        sync.RWMutex
	snapshot  dashboardSnapshot
	expiresAt time.Time
}

func (c *dashboardSnapshotCache) get() (dashboardSnapshot, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.expiresAt.IsZero() || time.Now().After(c.expiresAt) {
		return dashboardSnapshot{}, false
	}
	return c.snapshot, true
}

func (c *dashboardSnapshotCache) set(snapshot dashboardSnapshot, ttl time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.snapshot = snapshot
	c.expiresAt = time.Now().Add(ttl)
}

type liveSafetyGate struct {
	buildMode                  string
	enabled                    bool
	canary                     bool
	manualCanaryOverride       bool
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
	gate.manualCanaryOverride = envAffirmative(os.Getenv(manualCanaryOverrideEnv))
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

func envAffirmative(value string) bool {
	switch strings.ToUpper(strings.TrimSpace(value)) {
	case "1", "TRUE", "YES", "ON":
		return true
	default:
		return false
	}
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

func positiveOrDefault(value int, fallback int) int {
	if value > 0 {
		return value
	}
	return fallback
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
		ManualCanaryOverride:  g.manualCanaryOverride,
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

func (g *liveSafetyGate) canaryBlockers() []string {
	blockers := g.blockers()
	if g == nil || !g.canary || !g.manualCanaryOverride {
		return blockers
	}
	filtered := make([]string, 0, len(blockers))
	for _, blocker := range blockers {
		if blocker == "live.enabled=false" {
			continue
		}
		filtered = append(filtered, blocker)
	}
	sort.Strings(filtered)
	return filtered
}

func (g *liveSafetyGate) canaryReadiness() dashboardLiveReadiness {
	readiness := g.readiness()
	blockers := g.canaryBlockers()
	readiness.Blockers = blockers
	readiness.Ready = len(blockers) == 0
	return readiness
}

func (g *liveSafetyGate) requireManualCanary(action string) error {
	if g == nil {
		return fmt.Errorf("%s blocked: live gate not initialized", action)
	}
	if !g.canary {
		return fmt.Errorf("%s requires live.canary=true", action)
	}
	if !g.enabled && !g.manualCanaryOverride {
		return fmt.Errorf("%s blocked: live.enabled=false and %s=YES is required", action, manualCanaryOverrideEnv)
	}
	if blockers := g.canaryBlockers(); len(blockers) > 0 {
		return fmt.Errorf("%s blocked: %s", action, strings.Join(blockers, "; "))
	}
	return nil
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

func sanitizeEndpointForLog(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	parsed, err := url.Parse(trimmed)
	if err != nil {
		return "redacted"
	}
	host := parsed.Hostname()
	if host == "" {
		return "redacted"
	}
	if parsed.Path == "" && parsed.RawQuery == "" {
		return host
	}
	sum := sha256.Sum256([]byte(parsed.Path + "?" + parsed.RawQuery))
	return fmt.Sprintf("%s#%s", host, hex.EncodeToString(sum[:])[:8])
}

func pctOrDefault(value int, fallback string) domain.Decimal {
	if value <= 0 {
		return domain.MustDecimal(fallback)
	}
	return domain.NewDecimalFromInt(int64(value)).Div(domain.NewDecimalFromInt(100))
}

func riskConfigFromSettings(cfg *config.Config) risk.RiskConfig {
	if cfg == nil {
		return risk.DefaultRiskConfig()
	}
	return risk.RiskConfig{
		VaRWarnPct:        pctOrDefault(cfg.Risk.VarWarnPct, "0.08"),
		VaRKillPct:        pctOrDefault(cfg.Risk.VarKillPct, "0.12"),
		DailyDDKillPct:    pctOrDefault(cfg.Risk.DailyDDKillPct, "0.05"),
		WeeklyDDFreezePct: pctOrDefault(cfg.Risk.WeeklyDDFreezePct, "0.10"),
		TotalExposurePct:  pctOrDefault(cfg.Risk.TotalExposurePct, "0.30"),
		MaxSingleTradeUSD: domain.NewDecimalFromFloat(positiveFloatOrDefault(cfg.Live.MaxOrderUSD, 1)),
	}
}

func allocationConfigFromSettings(cfg *config.Config) risk.AllocationConfig {
	defaults := risk.DefaultAllocationConfig()
	if cfg == nil {
		return defaults
	}
	defaults.TierALimit = domain.NewDecimalFromFloat(positiveFloatOrDefault(cfg.TierA.MaxPerPoolUSD, 1))
	defaults.TierBLimit = domain.NewDecimalFromFloat(positiveFloatOrDefault(cfg.TierB.MaxPerPoolUSD, 1))
	defaults.TierCLimit = domain.NewDecimalFromFloat(positiveFloatOrDefault(cfg.TierC.MaxPerPoolUSD, 1))
	defaults.MaxExposure = pctOrDefault(cfg.Risk.TotalExposurePct, "0.30")
	return defaults
}

func positiveFloatOrDefault(value float64, fallback float64) float64 {
	if value > 0 {
		return value
	}
	return fallback
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
	app.alerter = initAlerter(logger, cfg)
	defer app.cleanup()

	// Initialize adapters
	if err := app.initAdapters(ctx); err != nil {
		logger.Error("failed to initialize adapters", zap.Error(err))
		app.sendAlert(ports.AlertP0, "startup", fmt.Sprintf("adapter initialization failed: %v", err))
		return 1
	}

	// Initialize core modules
	if err := app.initCore(ctx); err != nil {
		logger.Error("failed to initialize core modules", zap.Error(err))
		app.sendAlert(ports.AlertP0, "startup", fmt.Sprintf("core initialization failed: %v", err))
		return 1
	}

	// Wire the main loop with all components (TR-01 wiring)
	if err := app.wireMainLoop(ctx); err != nil {
		logger.Error("failed to wire main loop", zap.Error(err))
		app.sendAlert(ports.AlertP0, "startup", fmt.Sprintf("main loop wiring failed: %v", err))
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
			zap.String("primary", sanitizeEndpointForLog(provider.Endpoint())),
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
	if err := app.ensureLiveSchema(ctx); err != nil {
		return err
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

func (app *App) ensureLiveSchema(ctx context.Context) error {
	if app == nil || app.config == nil || app.liveGate == nil || !app.liveGate.isExecutionMode() || !app.liveGate.enabled {
		return nil
	}
	backend := strings.ToLower(strings.TrimSpace(app.config.Store.Backend))
	if backend != "postgres" && backend != "postgresql" && backend != "pg" {
		return nil
	}
	dbStore, ok := any(app.store).(interface{ DB() *sql.DB })
	if !ok || dbStore.DB() == nil {
		return fmt.Errorf("live schema guard requires postgres store with DB access")
	}
	state, err := loadLiveSchemaState(ctx, dbStore.DB())
	if err != nil {
		return err
	}
	return validateLiveSchemaState(state)
}

func loadLiveSchemaState(ctx context.Context, db *sql.DB) (map[string]bool, error) {
	required := []string{
		"positions",
		"transactions",
		"canary_events",
		"pnl_ledger",
		"shadow_decision_trace",
		"idx_positions_one_active_per_pool",
	}
	state := make(map[string]bool, len(required))
	for _, relation := range required {
		var exists bool
		if err := db.QueryRowContext(ctx, `SELECT to_regclass($1) IS NOT NULL`, "public."+relation).Scan(&exists); err != nil {
			return nil, fmt.Errorf("live schema guard query failed for %s: %w", relation, err)
		}
		state[relation] = exists
	}
	return state, nil
}

func validateLiveSchemaState(state map[string]bool) error {
	required := []string{
		"positions",
		"transactions",
		"canary_events",
		"pnl_ledger",
		"shadow_decision_trace",
		"idx_positions_one_active_per_pool",
	}
	var missing []string
	for _, relation := range required {
		if !state[relation] {
			missing = append(missing, relation)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("live schema guard blocked startup; missing postgres relations: %s", strings.Join(missing, ", "))
	}
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
		PoolRepo:     app.store.PoolRepo(),
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
	riskConfig := riskConfigFromSettings(app.config)
	var riskRepo ports.RiskRepo
	if app.store != nil {
		riskRepo = app.store.RiskRepo()
	}
	riskGate := risk.NewRiskGateWithConfig(riskRepo, riskConfig)
	if app.logger != nil {
		app.logger.Info("RiskGate wired (fail-closed enabled)",
			zap.Bool("risk_repo_attached", riskRepo != nil))
	}

	// Wrap RiskGate with adapter to satisfy loop.RiskGate interface
	riskGateAdapter := &riskGateAdapter{riskGate: riskGate}

	// Create AllocationManager with config from settings
	allocConfig := allocationConfigFromSettings(app.config)
	allocManager := risk.NewAllocationManagerWithRepo(allocConfig, app.store.PositionRepo())
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
		npmBaseAddress:      strings.TrimSpace(app.config.Execution.NPMBaseAddress),
		txDeadlineSeconds:   positiveOrDefault(app.config.Execution.TxDeadlineSeconds, 300),
		exitDeadlineSeconds: positiveOrDefault(app.config.Execution.ExitDeadlineSeconds, 600),
		signTimeoutSeconds:  positiveOrDefault(app.config.Execution.SignTimeoutSeconds, 45),
		sendTimeoutSeconds:  positiveOrDefault(app.config.Execution.SendTimeoutSeconds, 180),
		mintSlippageBps:     positiveOrDefault(app.config.Execution.MintSlippageBps, 9999),
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
	var txRepo ports.TxRepo
	if app.store != nil {
		txRepo = app.store.TxRepo()
	}
	app.watchdog = watchdog.NewDefaultWatchdogWithDependencies(riskGate, txRepo)

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

	// Scanner heartbeat worker keeps pool cache warm and provides additional
	// evidence when external issues appear in scan steps.
	app.wg.Add(1)
	go func() {
		defer app.wg.Done()
		app.runScannerLoop(ctx)
	}()

	if app.watchdog != nil {
		app.wg.Add(1)
		go func() {
			defer app.wg.Done()
			if err := app.watchdog.Run(ctx); err != nil && ctx.Err() == nil {
				app.logger.Error("watchdog exited", zap.Error(err))
				app.sendAlert(ports.AlertP1, "watchdog", fmt.Sprintf("watchdog exited: %v", err))
			}
		}()
	}

	app.logger.Info("workers started",
		zap.String("strategy_interval", "1m"),
		zap.String("scanner_interval", "5m"))
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
				app.sendAlert(ports.AlertP1, "scanner", fmt.Sprintf("scanner run failed: %v", err))
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
		app.sendAlert(ports.AlertP1, "shadow_strategy_scan", fmt.Sprintf("scanner ScanOnce failed: %v", err))
		return
	}
	scoredPools = app.extendShadowScoredPoolsWithActivePositions(ctx, scoredPools)
	if len(scoredPools) == 0 {
		app.logger.Info("shadow scan completed with no candidates")
		return
	}

	pools := make([]domain.Pool, 0, len(scoredPools))
	scores := make(map[string]domain.Score, len(scoredPools))
	for _, scored := range scoredPools {
		pools = append(pools, scored.Pool)
		scores[scored.Pool.Key()] = scored.Score
	}

	candidates := selectShadowCandidatesByScore(scoredPools, shadowCandidateLimit)
	candidates = app.extendShadowCandidatesWithActivePositions(ctx, scoredPools, candidates)

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
			trace.IntentReason = "pool not selected for strategy evaluation"
			trace.PipelineStage = "candidate_filtered"
			trace.PipelineReason = trace.SelectionReason
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
			app.sendAlert(ports.AlertP1, "shadow_strategy", fmt.Sprintf("strategy evaluation failed: pool=%s reason=%s", pool.Key(), err))
			app.logger.Warn("shadow strategy evaluation failed",
				zap.String("pool", pool.Key()),
				zap.Error(err))
			continue
		}
		if intent == nil {
			trace.IntentReason = fmt.Sprintf("score threshold not met: total %.1f < %.0f", score.ComputeTotal(), shadowOpenScoreThreshold)
			trace.PipelineStage = "strategy_declined"
			trace.PipelineReason = trace.IntentReason
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

		app.sendAlert(ports.AlertP1, "shadow_pipeline", fmt.Sprintf("pipeline reject pool=%s stage=%s reason=%s", pool.Key(), pipeline.Stage, pipeline.Reason))
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

func (app *App) extendShadowScoredPoolsWithActivePositions(ctx context.Context, scoredPools []scanner.ScoredPool) []scanner.ScoredPool {
	if app == nil || app.store == nil || app.store.PositionRepo() == nil || app.store.PoolRepo() == nil || len(scoredPools) == 0 {
		return scoredPools
	}

	scoredByRef := make(map[string]struct{}, len(scoredPools))
	chains := make(map[domain.ChainID]struct{})
	for _, scored := range scoredPools {
		scoredByRef[shadowCandidatePoolRef(scored.Pool.Chain, scored.Pool.ID)] = struct{}{}
		chains[scored.Pool.Chain] = struct{}{}
	}

	storePoolsByRef := make(map[string]domain.Pool)
	for chain := range chains {
		pools, err := app.store.PoolRepo().ListPools(ctx, ports.PoolFilter{Chain: chain, Limit: 1000})
		if err != nil {
			app.logger.Warn("shadow active pool universe lookup failed",
				zap.String("chain", string(chain)),
				zap.Error(err))
			continue
		}
		for _, pool := range pools {
			storePoolsByRef[shadowCandidatePoolRef(pool.Chain, pool.ID)] = pool
		}
	}

	for chain := range chains {
		for _, status := range []domain.PositionStatus{domain.StatusOpening, domain.StatusOpen} {
			positions, err := app.store.PositionRepo().FindByChainAndStatus(ctx, chain, status)
			if err != nil {
				app.logger.Warn("shadow active position candidate lookup failed",
					zap.String("chain", string(chain)),
					zap.String("status", string(status)),
					zap.Error(err))
				continue
			}
			for _, pos := range positions {
				ref := shadowCandidatePoolRef(pos.Chain, pos.PoolID)
				if _, exists := scoredByRef[ref]; exists {
					continue
				}
				pool, ok := storePoolsByRef[ref]
				if !ok {
					continue
				}
				history, err := app.store.PoolRepo().GetScoreHistory(ctx, pool.Key(), 0)
				if err != nil || len(history) == 0 {
					if err != nil {
						app.logger.Warn("shadow active pool score history lookup failed",
							zap.String("pool", pool.Key()),
							zap.Error(err))
					}
					continue
				}
				latest := history[len(history)-1]
				scoredPools = append(scoredPools, scanner.ScoredPool{
					Pool:  pool,
					Score: latest.Score,
				})
				scoredByRef[ref] = struct{}{}
				app.logger.Info("shadow injected active pool into scored universe",
					zap.String("pool", pool.Key()),
					zap.String("status", string(status)),
					zap.Float64("score_total", latest.Score.ComputeTotal()))
			}
		}
	}

	return scoredPools
}

func (app *App) extendShadowCandidatesWithActivePositions(ctx context.Context, scoredPools []scanner.ScoredPool, candidates []domain.Pool) []domain.Pool {
	if app == nil || app.store == nil || app.store.PositionRepo() == nil || len(scoredPools) == 0 {
		return candidates
	}

	scoredByRef := make(map[string]domain.Pool, len(scoredPools))
	chains := make(map[domain.ChainID]struct{})
	for _, scored := range scoredPools {
		ref := shadowCandidatePoolRef(scored.Pool.Chain, scored.Pool.ID)
		scoredByRef[ref] = scored.Pool
		chains[scored.Pool.Chain] = struct{}{}
	}

	candidateSet := make(map[string]struct{}, len(candidates))
	for _, pool := range candidates {
		candidateSet[shadowCandidatePoolRef(pool.Chain, pool.ID)] = struct{}{}
	}

	for chain := range chains {
		for _, status := range []domain.PositionStatus{domain.StatusOpening, domain.StatusOpen} {
			positions, err := app.store.PositionRepo().FindByChainAndStatus(ctx, chain, status)
			if err != nil {
				app.logger.Warn("shadow active position candidate lookup failed",
					zap.String("chain", string(chain)),
					zap.String("status", string(status)),
					zap.Error(err))
				continue
			}
			for _, pos := range positions {
				ref := shadowCandidatePoolRef(pos.Chain, pos.PoolID)
				if _, exists := candidateSet[ref]; exists {
					continue
				}
				pool, ok := scoredByRef[ref]
				if !ok {
					continue
				}
				candidates = append(candidates, pool)
				candidateSet[ref] = struct{}{}
			}
		}
	}

	return candidates
}

func shadowCandidatePoolRef(chain domain.ChainID, poolID string) string {
	return strings.ToLower(strings.TrimSpace(string(chain))) + "|" + strings.ToLower(strings.TrimSpace(poolID))
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
	broadcaster         ports.Broadcaster
	requiredConfs       int
	riskGate            *risk.RiskGate
	store               ports.Store
	liveGate            *liveSafetyGate
	provider            *rpc.RoundRobinProvider
	wallet              ports.Wallet
	walletAddress       domain.Address
	npmBaseAddress      string
	txDeadlineSeconds   int
	exitDeadlineSeconds int
	signTimeoutSeconds  int
	sendTimeoutSeconds  int
	mintSlippageBps     int
}

func (o *orderManagerAdapter) Open(ctx context.Context, pool domain.Pool, amountUSD domain.Decimal) (loop.ExecutionResult, error) {
	if o.store == nil {
		return loop.ExecutionResult{Success: false, Error: "store not configured"}, nil
	}
	shadowExecution := o.liveGate == nil || !o.liveGate.isExecutionMode()
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
			if shadowExecution && existing[0].Status != domain.StatusOpen {
				if err := o.store.PositionRepo().UpdateStatus(ctx, existing[0].ID, domain.StatusOpen); err != nil {
					return loop.ExecutionResult{}, err
				}
				existing[0].Status = domain.StatusOpen
			}
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
		position.Status = domain.StatusApproved
		if result, handled, err := o.saveNewPosition(ctx, pool.ID, position); handled {
			return result, err
		}
		if err := o.store.TxRepo().UpsertTx(ctx, signed); err != nil {
			return loop.ExecutionResult{}, err
		}
		if err := o.broadcaster.Send(ctx, signed); err != nil {
			signed.Status = domain.TxFailed
			_ = o.store.TxRepo().UpsertTx(ctx, signed)
			return loop.ExecutionResult{Success: false, Error: fmt.Sprintf("broadcast failed: %v", err)}, nil
		}
		signed.Status = txStatusAfterLiveSend(o.broadcaster, o.requiredConfs)
		if err := o.store.TxRepo().UpsertTx(ctx, signed); err != nil {
			return loop.ExecutionResult{}, err
		}
		finalStatus := domain.StatusOpening
		if err := o.store.PositionRepo().UpdateStatus(ctx, positionID, finalStatus); err != nil {
			return loop.ExecutionResult{}, err
		}
		position.Status = finalStatus
		if broadcasterConfirmsOnSend(o.broadcaster, o.requiredConfs) {
			finalStatus = domain.StatusOpen
			if err := o.store.PositionRepo().UpdateStatus(ctx, positionID, finalStatus); err != nil {
				return loop.ExecutionResult{}, err
			}
			position.Status = finalStatus
		}
		tx = signed
		txHash = signed.Hash
	} else {
		if result, handled, err := o.saveNewPosition(ctx, pool.ID, position); handled {
			return result, err
		}
		if shadowExecution {
			if err := o.store.PositionRepo().UpdateStatus(ctx, positionID, domain.StatusOpen); err != nil {
				return loop.ExecutionResult{}, err
			}
			position.Status = domain.StatusOpen
		}
		if err := o.store.TxRepo().UpsertTx(ctx, tx); err != nil {
			return loop.ExecutionResult{}, err
		}
	}

	return loop.ExecutionResult{
		TxHash:      txHash,
		Success:     true,
		PositionID:  positionID,
		FinalStatus: position.Status,
	}, nil
}

func (o *orderManagerAdapter) saveNewPosition(ctx context.Context, poolID string, position *domain.Position) (loop.ExecutionResult, bool, error) {
	if err := o.store.PositionRepo().Save(ctx, position); err != nil {
		if !isActivePositionConstraintError(err) {
			return loop.ExecutionResult{}, true, err
		}
		existing, lookupErr := o.findExistingActivePosition(ctx, poolID)
		if lookupErr != nil {
			return loop.ExecutionResult{}, true, lookupErr
		}
		if existing == nil {
			return loop.ExecutionResult{}, true, err
		}
		return loop.ExecutionResult{
			Success:     true,
			PositionID:  existing.ID,
			FinalStatus: existing.Status,
		}, true, nil
	}
	return loop.ExecutionResult{}, false, nil
}

func (o *orderManagerAdapter) findExistingActivePosition(ctx context.Context, poolID string) (*domain.Position, error) {
	for _, status := range []domain.PositionStatus{
		domain.StatusIntended,
		domain.StatusApproved,
		domain.StatusOpening,
		domain.StatusOpen,
		domain.StatusExiting,
	} {
		existing, err := o.store.PositionRepo().FindByPoolAndStatus(ctx, poolID, status)
		if err != nil {
			return nil, err
		}
		if len(existing) > 0 {
			return existing[0], nil
		}
	}
	return nil, nil
}

func isActivePositionConstraintError(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	return strings.Contains(msg, "idx_positions_one_active_per_pool") ||
		(strings.Contains(msg, ".chain, ") && strings.Contains(msg, ".pool_id")) ||
		strings.Contains(msg, "positions.chain, positions.pool_id")
}

func (o *orderManagerAdapter) Close(ctx context.Context, positionID string) (loop.ExecutionResult, error) {
	if o == nil || o.store == nil {
		return loop.ExecutionResult{Success: false, Error: "store not configured"}, nil
	}
	position, err := o.store.PositionRepo().FindByID(ctx, positionID)
	if err != nil {
		return loop.ExecutionResult{}, err
	}
	if position == nil {
		return loop.ExecutionResult{Success: false, Error: "position not found", PositionID: positionID}, nil
	}
	if o != nil && o.liveGate != nil && o.liveGate.isExecutionMode() {
		return o.closeLiveCanaryPosition(ctx, position)
	}
	if position.Status == domain.StatusClosed {
		return loop.ExecutionResult{
			Success:     true,
			PositionID:  positionID,
			FinalStatus: domain.StatusClosed,
		}, nil
	}
	if position.Status != domain.StatusExiting {
		if !position.Status.CanTransitionTo(domain.StatusExiting) {
			return loop.ExecutionResult{
				Success:     false,
				Error:       fmt.Sprintf("cannot transition from %s to exiting", position.Status),
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		if err := o.store.PositionRepo().UpdateStatus(ctx, positionID, domain.StatusExiting); err != nil {
			return loop.ExecutionResult{}, err
		}
		position.Status = domain.StatusExiting
	}
	txHash, err := o.persistShadowAuditTx(ctx, position, "close")
	if err != nil {
		return loop.ExecutionResult{}, err
	}
	if err := o.store.PositionRepo().UpdateStatus(ctx, positionID, domain.StatusClosed); err != nil {
		return loop.ExecutionResult{}, err
	}
	return loop.ExecutionResult{
		TxHash:      txHash,
		Success:     true,
		PositionID:  positionID,
		FinalStatus: domain.StatusClosed,
	}, nil
}

func (o *orderManagerAdapter) closeLiveCanaryPosition(ctx context.Context, position *domain.Position) (loop.ExecutionResult, error) {
	if position == nil {
		return loop.ExecutionResult{Success: false, Error: "position not found"}, nil
	}
	if o.wallet == nil || o.broadcaster == nil || o.provider == nil {
		return loop.ExecutionResult{
			Success:     false,
			Error:       "live close components not configured",
			PositionID:  position.ID,
			FinalStatus: position.Status,
		}, nil
	}
	if strings.TrimSpace(position.TokenID) == "" {
		return loop.ExecutionResult{
			Success:     false,
			Error:       "live close requires position token_id",
			PositionID:  position.ID,
			FinalStatus: position.Status,
		}, nil
	}
	if err := checkLiveCloseGate(o.liveGate, domain.Pool{ID: position.PoolID, Chain: position.Chain}); err != nil {
		return loop.ExecutionResult{
			Success:     false,
			Error:       err.Error(),
			PositionID:  position.ID,
			FinalStatus: position.Status,
		}, nil
	}
	if position.Status == domain.StatusClosed {
		return loop.ExecutionResult{
			Success:     true,
			PositionID:  position.ID,
			FinalStatus: domain.StatusClosed,
		}, nil
	}
	if position.Status != domain.StatusExiting {
		if !position.Status.CanTransitionTo(domain.StatusExiting) {
			return loop.ExecutionResult{
				Success:     false,
				Error:       fmt.Sprintf("cannot transition from %s to exiting", position.Status),
				PositionID:  position.ID,
				FinalStatus: position.Status,
			}, nil
		}
		if err := o.store.PositionRepo().UpdateStatus(ctx, position.ID, domain.StatusExiting); err != nil {
			return loop.ExecutionResult{}, err
		}
		position.Status = domain.StatusExiting
	}

	state, err := o.loadLiveNPMPositionState(ctx, position)
	if err != nil {
		_ = o.store.PositionRepo().UpdateStatus(ctx, position.ID, domain.StatusExitFailed)
		return loop.ExecutionResult{
			Success:     false,
			Error:       err.Error(),
			PositionID:  position.ID,
			FinalStatus: domain.StatusExitFailed,
		}, nil
	}

	decreaseData := encodeLiveCloseDecreaseCalldata(
		mustLiveCloseTokenIDBig(position.TokenID),
		state.Liquidity,
		big.NewInt(0),
		big.NewInt(0),
		big.NewInt(time.Now().Add(time.Duration(o.exitDeadlineSeconds)*time.Second).Unix()),
	)
	decreaseTx := buildLiveCloseUnsignedTx(o.npmBaseAddress, o.wallet.Address(), decreaseData, "live-exit-decrease-"+position.TokenID, o.exitDeadlineSeconds)
	decreaseSigned, err := sendLiveCloseTx(ctx, o.wallet, o.broadcaster, decreaseTx, "decrease_liquidity", o.signTimeoutSeconds, o.sendTimeoutSeconds, o.requiredConfs)
	if err != nil {
		if decreaseSigned.ID != "" {
			_ = o.store.TxRepo().UpsertTx(ctx, decreaseSigned)
		}
		_ = o.store.PositionRepo().UpdateStatus(ctx, position.ID, domain.StatusExitFailed)
		return loop.ExecutionResult{
			Success:     false,
			Error:       err.Error(),
			PositionID:  position.ID,
			FinalStatus: domain.StatusExitFailed,
		}, nil
	}
	if err := o.store.TxRepo().UpsertTx(ctx, decreaseSigned); err != nil {
		return loop.ExecutionResult{}, err
	}

	maxUint128 := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1))
	collectData := encodeLiveCloseCollectCalldata(
		mustLiveCloseTokenIDBig(position.TokenID),
		common.HexToAddress(o.wallet.Address().String()),
		maxUint128,
		maxUint128,
	)
	collectTx := buildLiveCloseUnsignedTx(o.npmBaseAddress, o.wallet.Address(), collectData, "live-exit-collect-"+position.TokenID, o.exitDeadlineSeconds)
	collectSigned, err := sendLiveCloseTx(ctx, o.wallet, o.broadcaster, collectTx, "collect", o.signTimeoutSeconds, o.sendTimeoutSeconds, o.requiredConfs)
	if err != nil {
		if collectSigned.ID != "" {
			_ = o.store.TxRepo().UpsertTx(ctx, collectSigned)
		}
		_ = o.store.PositionRepo().UpdateStatus(ctx, position.ID, domain.StatusExitFailed)
		return loop.ExecutionResult{
			TxHash:      decreaseSigned.Hash,
			Success:     false,
			Error:       err.Error(),
			PositionID:  position.ID,
			FinalStatus: domain.StatusExitFailed,
		}, nil
	}
	if err := o.store.TxRepo().UpsertTx(ctx, collectSigned); err != nil {
		return loop.ExecutionResult{}, err
	}
	if broadcasterConfirmsOnSend(o.broadcaster, o.requiredConfs) {
		if err := o.store.PositionRepo().UpdateStatus(ctx, position.ID, domain.StatusClosed); err != nil {
			return loop.ExecutionResult{}, err
		}
		return loop.ExecutionResult{
			TxHash:      collectSigned.Hash,
			Success:     true,
			PositionID:  position.ID,
			FinalStatus: domain.StatusClosed,
		}, nil
	}
	return loop.ExecutionResult{
		TxHash:      collectSigned.Hash,
		Success:     true,
		PositionID:  position.ID,
		FinalStatus: domain.StatusExiting,
	}, nil
}

func (o *orderManagerAdapter) Rebalance(ctx context.Context, positionID string, newLower, newUpper int64) (loop.ExecutionResult, error) {
	if o == nil || o.store == nil {
		return loop.ExecutionResult{Success: false, Error: "store not configured"}, nil
	}
	position, err := o.store.PositionRepo().FindByID(ctx, positionID)
	if err != nil {
		return loop.ExecutionResult{}, err
	}
	if position == nil {
		return loop.ExecutionResult{Success: false, Error: "position not found", PositionID: positionID}, nil
	}
	if o != nil && o.liveGate != nil && o.liveGate.isExecutionMode() {
		if o.wallet == nil || o.broadcaster == nil || o.provider == nil {
			return loop.ExecutionResult{
				Success:     false,
				Error:       "live rebalance components not configured",
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		if position.Status != domain.StatusOpen {
			return loop.ExecutionResult{
				Success:     false,
				Error:       fmt.Sprintf("cannot rebalance position in %s state", position.Status),
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		pool, err := o.loadPoolForPosition(ctx, position)
		if err != nil {
			return loop.ExecutionResult{
				Success:     false,
				Error:       err.Error(),
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		closeResult, err := o.closeLiveCanaryPosition(ctx, position)
		if err != nil {
			return loop.ExecutionResult{}, err
		}
		if !closeResult.Success {
			return closeResult, nil
		}

		now := time.Now()
		newPositionID := shadowID("rebalance-pos", pool.Key(), now.Unix())
		reopened := &domain.Position{
			ID:        newPositionID,
			PoolID:    pool.ID,
			Chain:     pool.Chain,
			Status:    domain.StatusApproved,
			Tier:      pool.Tier_,
			AmountUSD: position.AmountUSD,
			TickLower: newLower,
			TickUpper: newUpper,
			OpenedAt:  now.Unix(),
		}
		prepared, err := o.buildPreparedMintTxWithTicks(ctx, pool, position.AmountUSD, newPositionID, now, newLower, newUpper)
		if err != nil {
			reopened.Status = domain.StatusRejected
			_ = o.store.PositionRepo().Save(ctx, reopened)
			return loop.ExecutionResult{
				TxHash:      closeResult.TxHash,
				Success:     false,
				Error:       fmt.Sprintf("rebalance reopen build failed after close: %v", err),
				PositionID:  closeResult.PositionID,
				FinalStatus: domain.StatusClosed,
			}, nil
		}
		if err := o.preflightPreparedTx(ctx, prepared.UnsignedTx); err != nil {
			reopened.Status = domain.StatusRejected
			_ = o.store.PositionRepo().Save(ctx, reopened)
			return loop.ExecutionResult{
				TxHash:      closeResult.TxHash,
				Success:     false,
				Error:       fmt.Sprintf("rebalance reopen preflight failed after close: %v", err),
				PositionID:  closeResult.PositionID,
				FinalStatus: domain.StatusClosed,
			}, nil
		}
		signed, err := o.wallet.Sign(ctx, prepared.UnsignedTx)
		if err != nil {
			reopened.Status = domain.StatusRejected
			_ = o.store.PositionRepo().Save(ctx, reopened)
			return loop.ExecutionResult{
				TxHash:      closeResult.TxHash,
				Success:     false,
				Error:       fmt.Sprintf("rebalance reopen sign failed after close: %v", err),
				PositionID:  closeResult.PositionID,
				FinalStatus: domain.StatusClosed,
			}, nil
		}
		signed.ID = prepared.ID
		signed.Status = domain.TxBuilt
		if err := o.store.PositionRepo().Save(ctx, reopened); err != nil {
			return loop.ExecutionResult{}, err
		}
		if err := o.store.TxRepo().UpsertTx(ctx, signed); err != nil {
			return loop.ExecutionResult{}, err
		}
		if err := o.broadcaster.Send(ctx, signed); err != nil {
			signed.Status = domain.TxFailed
			_ = o.store.TxRepo().UpsertTx(ctx, signed)
			_ = o.store.PositionRepo().UpdateStatus(ctx, newPositionID, domain.StatusRejected)
			return loop.ExecutionResult{
				TxHash:      closeResult.TxHash,
				Success:     false,
				Error:       fmt.Sprintf("rebalance reopen broadcast failed after close: %v", err),
				PositionID:  closeResult.PositionID,
				FinalStatus: domain.StatusClosed,
			}, nil
		}
		signed.Status = txStatusAfterLiveSend(o.broadcaster, o.requiredConfs)
		if err := o.store.TxRepo().UpsertTx(ctx, signed); err != nil {
			return loop.ExecutionResult{}, err
		}
		if err := o.store.PositionRepo().UpdateStatus(ctx, newPositionID, domain.StatusOpening); err != nil {
			return loop.ExecutionResult{}, err
		}
		if broadcasterConfirmsOnSend(o.broadcaster, o.requiredConfs) {
			if err := o.store.PositionRepo().UpdateStatus(ctx, newPositionID, domain.StatusOpen); err != nil {
				return loop.ExecutionResult{}, err
			}
			return loop.ExecutionResult{
				TxHash:      signed.Hash,
				Success:     true,
				PositionID:  newPositionID,
				FinalStatus: domain.StatusOpen,
			}, nil
		}
		return loop.ExecutionResult{
			TxHash:      signed.Hash,
			Success:     true,
			PositionID:  newPositionID,
			FinalStatus: domain.StatusOpening,
		}, nil
	}
	if position.Status != domain.StatusOpen {
		return loop.ExecutionResult{
			Success:     false,
			Error:       fmt.Sprintf("cannot rebalance position in %s state", position.Status),
			PositionID:  positionID,
			FinalStatus: position.Status,
		}, nil
	}
	position.TickLower = newLower
	position.TickUpper = newUpper
	if err := o.store.PositionRepo().Save(ctx, position); err != nil {
		return loop.ExecutionResult{}, err
	}
	txHash, err := o.persistShadowAuditTx(ctx, position, "rebalance")
	if err != nil {
		return loop.ExecutionResult{}, err
	}
	return loop.ExecutionResult{
		TxHash:      txHash,
		Success:     true,
		PositionID:  positionID,
		FinalStatus: domain.StatusOpen,
	}, nil
}

func (o *orderManagerAdapter) loadPoolForPosition(ctx context.Context, position *domain.Position) (domain.Pool, error) {
	if o == nil || o.store == nil || position == nil {
		return domain.Pool{}, fmt.Errorf("pool lookup unavailable")
	}
	pools, err := o.store.PoolRepo().ListPools(ctx, ports.PoolFilter{Chain: position.Chain})
	if err != nil {
		return domain.Pool{}, err
	}
	for _, pool := range pools {
		if strings.EqualFold(strings.TrimSpace(pool.ID), strings.TrimSpace(position.PoolID)) {
			if pool.Tick == 0 {
				poolAddr, parseErr := domain.ParseAddress(pool.ID)
				if parseErr == nil && o.provider != nil {
					if tick, tickErr := readV3PoolTickForMark(ctx, o.provider, poolAddr); tickErr == nil {
						pool.Tick = tick
					}
				}
			}
			return pool, nil
		}
	}
	return domain.Pool{}, fmt.Errorf("pool not found for position %s", position.ID)
}

func (o *orderManagerAdapter) CollectFees(ctx context.Context, positionID string) (loop.ExecutionResult, error) {
	if o == nil || o.store == nil {
		return loop.ExecutionResult{Success: false, Error: "store not configured"}, nil
	}
	position, err := o.store.PositionRepo().FindByID(ctx, positionID)
	if err != nil {
		return loop.ExecutionResult{}, err
	}
	if position == nil {
		return loop.ExecutionResult{Success: false, Error: "position not found", PositionID: positionID}, nil
	}
	if o != nil && o.liveGate != nil && o.liveGate.isExecutionMode() {
		if o.wallet == nil || o.broadcaster == nil {
			return loop.ExecutionResult{
				Success:     false,
				Error:       "live fee collection components not configured",
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		if strings.TrimSpace(position.TokenID) == "" {
			return loop.ExecutionResult{
				Success:     false,
				Error:       "live fee collection requires position token_id",
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		if position.Status != domain.StatusOpen {
			return loop.ExecutionResult{
				Success:     false,
				Error:       fmt.Sprintf("cannot collect fees from position in %s state", position.Status),
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		if err := checkLiveCloseGate(o.liveGate, domain.Pool{ID: position.PoolID, Chain: position.Chain}); err != nil {
			return loop.ExecutionResult{
				Success:     false,
				Error:       err.Error(),
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		maxUint128 := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1))
		collectData := encodeLiveCloseCollectCalldata(
			mustLiveCloseTokenIDBig(position.TokenID),
			common.HexToAddress(o.wallet.Address().String()),
			maxUint128,
			maxUint128,
		)
		collectTx := buildLiveCloseUnsignedTx(o.npmBaseAddress, o.wallet.Address(), collectData, "live-collect-"+position.TokenID, o.exitDeadlineSeconds)
		collectSigned, err := sendLiveCloseTx(ctx, o.wallet, o.broadcaster, collectTx, "collect", o.signTimeoutSeconds, o.sendTimeoutSeconds, o.requiredConfs)
		if err != nil {
			if collectSigned.ID != "" {
				_ = o.store.TxRepo().UpsertTx(ctx, collectSigned)
			}
			return loop.ExecutionResult{
				Success:     false,
				Error:       err.Error(),
				PositionID:  positionID,
				FinalStatus: position.Status,
			}, nil
		}
		if err := o.store.TxRepo().UpsertTx(ctx, collectSigned); err != nil {
			return loop.ExecutionResult{}, err
		}
		finalStatus := domain.StatusOpen
		if !broadcasterConfirmsOnSend(o.broadcaster, o.requiredConfs) {
			finalStatus = position.Status
		}
		return loop.ExecutionResult{
			TxHash:      collectSigned.Hash,
			Success:     true,
			PositionID:  positionID,
			FinalStatus: finalStatus,
		}, nil
	}
	if position.Status != domain.StatusOpen {
		return loop.ExecutionResult{
			Success:     false,
			Error:       fmt.Sprintf("cannot collect fees from position in %s state", position.Status),
			PositionID:  positionID,
			FinalStatus: position.Status,
		}, nil
	}
	txHash, err := o.persistShadowAuditTx(ctx, position, "collect")
	if err != nil {
		return loop.ExecutionResult{}, err
	}
	return loop.ExecutionResult{
		TxHash:      txHash,
		Success:     true,
		PositionID:  positionID,
		FinalStatus: domain.StatusOpen,
	}, nil
}

func (o *orderManagerAdapter) persistShadowAuditTx(ctx context.Context, position *domain.Position, action string) (string, error) {
	if o == nil || o.store == nil || position == nil {
		return "", nil
	}
	now := time.Now().Unix()
	txHash := shadowID(action+"-tx", position.ID, now)
	from := o.walletAddress
	if from.IsZero() {
		from = zeroEVMAddress()
	}
	tx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       txHash,
			Chain:    position.Chain,
			From:     from,
			To:       parseAddressOrZero(position.PoolID),
			Value:    domain.ZeroDecimal(),
			Deadline: now + 300,
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxConfirmed,
	}
	if err := o.store.TxRepo().UpsertTx(ctx, tx); err != nil {
		return "", err
	}
	return txHash, nil
}

func (o *orderManagerAdapter) loadLiveNPMPositionState(ctx context.Context, position *domain.Position) (npmPositionState, error) {
	if position == nil {
		return npmPositionState{}, fmt.Errorf("position is nil")
	}
	if position.Chain != domain.ChainBase {
		return npmPositionState{}, fmt.Errorf("live close only supports base chain")
	}
	if o == nil || o.provider == nil {
		return npmPositionState{}, fmt.Errorf("base rpc provider is not configured")
	}
	npmAddress := strings.TrimSpace(o.npmBaseAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	tokenID, ok := new(big.Int).SetString(strings.TrimSpace(position.TokenID), 10)
	if !ok || tokenID.Sign() <= 0 {
		return npmPositionState{}, fmt.Errorf("invalid npm token id %q", position.TokenID)
	}

	data := make([]byte, 4+32)
	copy(data[:4], common.FromHex("0x99fbab88"))
	copy(data[4+32-len(tokenID.Bytes()):], tokenID.Bytes())

	to := common.HexToAddress(npmAddress)
	raw, err := o.provider.CallContract(ctx, ethereum.CallMsg{
		To:   &to,
		Data: data,
	}, nil)
	if err != nil {
		return npmPositionState{}, fmt.Errorf("read npm positions(%s): %w", position.TokenID, err)
	}
	if len(raw) < 32*12 {
		return npmPositionState{}, fmt.Errorf("npm positions(%s) returned short response: %d bytes", position.TokenID, len(raw))
	}

	token0, err := domain.ParseAddress(common.BytesToAddress(raw[2*32+12 : 3*32]).Hex())
	if err != nil {
		return npmPositionState{}, fmt.Errorf("decode npm token0: %w", err)
	}
	token1, err := domain.ParseAddress(common.BytesToAddress(raw[3*32+12 : 4*32]).Hex())
	if err != nil {
		return npmPositionState{}, fmt.Errorf("decode npm token1: %w", err)
	}

	return npmPositionState{
		TokenID:                  position.TokenID,
		Token0:                   token0,
		Token1:                   token1,
		Fee:                      new(big.Int).SetBytes(raw[4*32 : 5*32]).Uint64(),
		TickLower:                decodeABIInt24(raw[5*32 : 6*32]),
		TickUpper:                decodeABIInt24(raw[6*32 : 7*32]),
		Liquidity:                new(big.Int).SetBytes(raw[7*32 : 8*32]),
		FeeGrowthInside0LastX128: new(big.Int).SetBytes(raw[8*32 : 9*32]),
		FeeGrowthInside1LastX128: new(big.Int).SetBytes(raw[9*32 : 10*32]),
		TokensOwed0:              new(big.Int).SetBytes(raw[10*32 : 11*32]),
		TokensOwed1:              new(big.Int).SetBytes(raw[11*32 : 12*32]),
	}, nil
}

func checkLiveCloseGate(gate *liveSafetyGate, pool domain.Pool) error {
	if gate == nil {
		return fmt.Errorf("live gate not initialized")
	}
	if gate.killSwitch {
		return fmt.Errorf("live gate blocked: live.kill_switch=true")
	}
	chain := strings.ToLower(strings.TrimSpace(string(pool.Chain)))
	if _, ok := gate.allowedChains[chain]; !ok {
		return fmt.Errorf("live gate blocked: chain %s not in allowed_chains", pool.Chain)
	}
	poolID := strings.ToLower(strings.TrimSpace(pool.ID))
	if _, ok := gate.allowedPools[poolID]; !ok {
		return fmt.Errorf("live gate blocked: pool %s not in allowed_pools", pool.ID)
	}
	return nil
}

func buildLiveCloseUnsignedTx(npmBaseAddress string, wallet domain.Address, data []byte, id string, deadlineSeconds int) domain.UnsignedTx {
	npmAddress := strings.TrimSpace(npmBaseAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	return domain.UnsignedTx{
		ID:       id,
		Chain:    domain.ChainBase,
		From:     wallet,
		To:       domain.MustParseAddress(npmAddress),
		Value:    domain.ZeroDecimal(),
		Data:     data,
		Deadline: time.Now().Add(time.Duration(positiveOrDefault(deadlineSeconds, 600)) * time.Second).Unix(),
		MinOut:   domain.ZeroDecimal(),
	}
}

func sendLiveCloseTx(ctx context.Context, wallet interface {
	Sign(context.Context, domain.UnsignedTx) (domain.SignedTx, error)
}, broadcaster interface {
	Send(context.Context, domain.SignedTx) error
}, tx domain.UnsignedTx, action string, signTimeoutSeconds int, sendTimeoutSeconds int, requiredConfs int) (domain.SignedTx, error) {
	signCtx, cancel := context.WithTimeout(ctx, time.Duration(positiveOrDefault(signTimeoutSeconds, 45))*time.Second)
	signed, err := wallet.Sign(signCtx, tx)
	cancel()
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("sign %s: %w", action, err)
	}
	signed.ID = tx.ID
	signed.Status = domain.TxBuilt
	sendCtx, cancel := context.WithTimeout(ctx, time.Duration(positiveOrDefault(sendTimeoutSeconds, 180))*time.Second)
	err = broadcaster.Send(sendCtx, signed)
	cancel()
	if err != nil {
		signed.Status = domain.TxFailed
		return signed, fmt.Errorf("broadcast %s: %w", action, err)
	}
	if aware, ok := broadcaster.(ports.Broadcaster); ok {
		signed.Status = txStatusAfterLiveSend(aware, requiredConfs)
	} else {
		signed.Status = domain.TxBroadcast
	}
	return signed, nil
}

func encodeLiveCloseDecreaseCalldata(tokenID *big.Int, liquidity *big.Int, amount0Min *big.Int, amount1Min *big.Int, deadline *big.Int) []byte {
	data := make([]byte, 0, 4+32*5)
	data = append(data, mustKeccak4("decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))")...)
	data = append(data, leftPadLiveCloseWord(tokenID)...)
	data = append(data, leftPadLiveCloseWord(liquidity)...)
	data = append(data, leftPadLiveCloseWord(amount0Min)...)
	data = append(data, leftPadLiveCloseWord(amount1Min)...)
	data = append(data, leftPadLiveCloseWord(deadline)...)
	return data
}

func encodeLiveCloseCollectCalldata(tokenID *big.Int, recipient common.Address, amount0Max *big.Int, amount1Max *big.Int) []byte {
	data := make([]byte, 0, 4+32*4)
	data = append(data, mustKeccak4("collect((uint256,address,uint128,uint128))")...)
	data = append(data, leftPadLiveCloseWord(tokenID)...)
	data = append(data, common.LeftPadBytes(recipient.Bytes(), 32)...)
	data = append(data, leftPadLiveCloseWord(amount0Max)...)
	data = append(data, leftPadLiveCloseWord(amount1Max)...)
	return data
}

func mustLiveCloseTokenIDBig(tokenID string) *big.Int {
	token, ok := new(big.Int).SetString(tokenID, 10)
	if !ok || token.Sign() <= 0 {
		panic("invalid token id")
	}
	return token
}

func leftPadLiveCloseWord(value *big.Int) []byte {
	if value == nil {
		value = big.NewInt(0)
	}
	return common.LeftPadBytes(value.Bytes(), 32)
}

func mustKeccak4(signature string) []byte {
	return crypto.Keccak256([]byte(signature))[:4]
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
	solanaReadiness := flag.Bool("solana-readiness", false, "Run Solana read-only RPC and simulation readiness checks")
	solanaQuoteReadiness := flag.Bool("solana-quote-readiness", false, "Run Solana read-only Jupiter route quote readiness checks")
	solanaQuoteInputMint := flag.String("solana-quote-input-mint", solanaUSDCAddress, "Solana quote input mint")
	solanaQuoteOutputMint := flag.String("solana-quote-output-mint", solanaWrappedSOLAddress, "Solana quote output mint")
	solanaQuoteAmountRaw := flag.String("solana-quote-amount-raw", "2500000", "Solana quote input amount in raw integer units")
	solanaQuoteSlippageBPS := flag.Int("solana-quote-slippage-bps", 100, "Solana quote slippage tolerance in basis points")
	solanaSwapBuildReadiness := flag.Bool("solana-swap-build-readiness", false, "Run Solana read-only Jupiter swap transaction build readiness checks without signing or broadcasting")
	solanaSwapSignReadiness := flag.Bool("solana-swap-sign-readiness", false, "Run Solana Jupiter swap sign readiness checks without broadcasting")
	solanaSwapCanary := flag.Bool("solana-swap-canary", false, "Run a tiny real Solana canary swap with signing and broadcast")
	solanaFundingPlan := flag.Bool("solana-funding-plan", false, "Run a Solana same-chain funding plan for a target mint amount using existing wallet assets only")
	solanaLPFundingPlan := flag.Bool("solana-lp-funding-plan", false, "Run a Solana same-chain LP pair funding plan for a SOL/USDC 50/50 target")
	solanaLPPreflight := flag.Bool("solana-lp-preflight", false, "Run a Solana read-only LP preflight for SOL/USDC using same-chain funding planning")
	solanaMeteoraLPPreflight := flag.Bool("solana-meteora-lp-preflight", false, "Run a Solana read-only Meteora DLMM LP preflight for an audited pool")
	solanaMeteoraLPBuildReadiness := flag.Bool("solana-meteora-lp-build-readiness", false, "Run a Solana read-only Meteora DLMM LP build and simulation readiness check for an audited pool")
	solanaLPClosePreflight := flag.Bool("solana-lp-close-preflight", false, "Run a Solana read-only close preflight for an existing SOL/USDC LP position")
	solanaLPPrefundCanary := flag.Bool("solana-lp-prefund-canary", false, "Run a tiny real Solana LP prefund canary swap only after LP preflight shows prefund is the last blocker")
	solanaLPOpenCanary := flag.Bool("solana-lp-open-canary", false, "Run a tiny real Solana LP open canary after prefund and LP preflight are fully ready")
	solanaLPCloseCanary := flag.Bool("solana-lp-close-canary", false, "Run a tiny real Solana LP close canary only after close preflight shows exit_now and an existing open position")
	solanaLPRealizedPnLReconcile := flag.Bool("solana-lp-realized-pnl-reconcile", false, "Reconcile a closed Solana LP lifecycle into realized pnl_ledger entries")
	solanaSwapInputMint := flag.String("solana-swap-input-mint", solanaWrappedSOLAddress, "Solana swap build input mint")
	solanaSwapOutputMint := flag.String("solana-swap-output-mint", solanaUSDCAddress, "Solana swap build output mint")
	solanaSwapAmountRaw := flag.String("solana-swap-amount-raw", "10000000", "Solana swap build input amount in raw integer units")
	solanaSwapUserPublicKey := flag.String("solana-swap-user-public-key", "", "Solana public key to use for swap build readiness; defaults to SOLANA_FEE_PAYER_ADDRESS")
	solanaSwapMaxPriorityLamports := flag.Uint64("solana-swap-max-priority-lamports", 500000, "Maximum priority fee lamports for Solana swap build readiness")
	solanaFundingReserveLamports := flag.Uint64("solana-funding-reserve-lamports", solanaFundingMinReserveLamports, "Minimum SOL lamports to reserve when planning same-chain Solana funding")
	solanaFundingLedgerPositionID := flag.String("solana-funding-ledger-position-id", "", "Optional position id used to write estimated funding costs into the ledger")
	solanaLPTotalUSD := flag.String("solana-lp-total-usd", "10", "Total USD notional for the SOL/USDC LP funding plan")
	solanaMeteoraLPPool := flag.String("solana-meteora-lp-pool", "", "Meteora DLMM pool id for read-only LP preflight")
	solanaMeteoraLPRangePct := flag.String("solana-meteora-lp-range-pct", "2.5", "Symmetric Meteora DLMM LP range percentage for preflight")
	solanaDiscoveryReadiness := flag.Bool("solana-discovery-readiness", false, "Run Solana read-only pool discovery readiness checks")
	solanaDiscoveryMinTVL := flag.String("solana-discovery-min-tvl", "100000", "Minimum Solana pool TVL in USD for discovery readiness")
	solanaDiscoveryMinVol24h := flag.String("solana-discovery-min-vol24h", "100000", "Minimum Solana pool 24h volume in USD for discovery readiness")
	solanaDiscoveryLimit := flag.Int("solana-discovery-limit", 10, "Maximum Solana pools to print during discovery readiness")
	solanaTierCDiscovery := flag.Bool("solana-tierc-discovery", false, "Run Solana read-only Tier C candidate discovery for aggressive LP scouting")
	solanaTierCMinTVL := flag.String("solana-tierc-min-tvl", "10000", "Minimum Solana Tier C pool TVL in USD")
	solanaTierCMaxTVL := flag.String("solana-tierc-max-tvl", "1500000", "Maximum Solana Tier C pool TVL in USD")
	solanaTierCMinVol24h := flag.String("solana-tierc-min-vol24h", "25000", "Minimum Solana Tier C pool 24h volume in USD")
	solanaTierCMinVolTVL := flag.String("solana-tierc-min-vol-tvl", "0.75", "Minimum Solana Tier C volume/TVL ratio")
	solanaTierCLimit := flag.Int("solana-tierc-limit", 10, "Maximum Solana Tier C pools to print during discovery")
	solanaTierCJSONOut := flag.String("solana-tierc-json-out", "", "Path to write JSON output file with Solana Tier C audit results")
	solanaTierCIncludeRejects := flag.Bool("solana-tierc-include-rejects", false, "Include rejected Solana Tier C candidates in console output")
	solanaTierCMajorOnly := flag.Bool("solana-tierc-major-only", true, "Only include Solana Tier C candidates where both tokens are major assets")
	solanaTierCProtocol := flag.String("solana-tierc-protocol", "", "Restrict Solana Tier C discovery to an exact protocol id such as meteora-dlmm")
	solanaTierCAuditPool := flag.String("solana-tierc-audit-pool", "", "Run read-only deep audit for a single Solana pool id")
	solanaTierCDeepAuditWatchlist := flag.String("solana-tierc-deep-audit-watchlist", "", "Run repeated read-only Solana Tier C deep audit sampling for comma-separated protocol:pool targets")
	solanaTierCDeepAuditRounds := flag.Int("solana-tierc-deep-audit-rounds", 3, "Number of repeated Solana Tier C deep audit rounds")
	solanaTierCDeepAuditIntervalSeconds := flag.Int("solana-tierc-deep-audit-interval-seconds", 60, "Seconds to wait between Solana Tier C deep audit rounds")
	baseTierCDiscovery := flag.Bool("base-tierc-discovery", false, "Run Base read-only Tier C candidate discovery for aggressive LP scouting")
	baseTierCMinTVL := flag.String("base-tierc-min-tvl", "25000", "Minimum Base Tier C pool TVL in USD")
	baseTierCMaxTVL := flag.String("base-tierc-max-tvl", "2500000", "Maximum Base Tier C pool TVL in USD")
	baseTierCMinVol24h := flag.String("base-tierc-min-vol24h", "50000", "Minimum Base Tier C pool 24h volume in USD")
	baseTierCMinVolTVL := flag.String("base-tierc-min-vol-tvl", "0.50", "Minimum Base Tier C volume/TVL ratio")
	baseTierCMinFeeAPR := flag.String("base-tierc-min-fee-apr", "0.25", "Minimum estimated Base Tier C fee APR as a decimal ratio")
	baseTierCLimit := flag.Int("base-tierc-limit", 10, "Maximum Base Tier C pools to print during discovery")
	baseTierCJSONOut := flag.String("base-tierc-json-out", "", "Path to write JSON output file with audit pack results")
	baseTierCIncludeRejects := flag.Bool("base-tierc-include-rejects", false, "Include rejected candidates in console output")
	baseTierCAuditPool := flag.String("base-tierc-audit-pool", "", "Run read-only deep audit for a single Base pool id")
	baseTierCHolderSnapshotRefresh := flag.Bool("base-tierc-holder-snapshot-refresh", false, "Refresh Base Tier C holder snapshot overrides from BaseScan token pages")
	baseTierCHolderSnapshotPath := flag.String("base-tierc-holder-snapshot-path", "", "Path to Tier C holder snapshot override JSON file")
	canaryPreflight := flag.Bool("canary-preflight", false, "Run a single Base canary preflight without signing or broadcasting")
	canaryPrepare := flag.Bool("canary-prepare", false, "Run a single Base canary prepare: wrap WETH and approve exact token amounts")
	canaryMint := flag.Bool("canary-mint", false, "Run a single Base canary Uniswap V3 mint")
	canaryReconcileMint := flag.Bool("canary-reconcile-mint", false, "Reconcile a Base canary mint receipt into the database")
	canaryExitPreflight := flag.Bool("canary-exit-preflight", false, "Run a single Base canary exit preflight without signing or broadcasting")
	canaryExit := flag.Bool("canary-exit", false, "Run a single guarded Base canary Uniswap V3 exit")
	canaryTokenID := flag.String("token-id", "", "Uniswap V3 NFT token ID for canary exit preflight")
	canaryTxHash := flag.String("tx-hash", "", "Transaction hash for canary receipt reconciliation")
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
	configureTierCPathEnv(*configPath)
	if strings.TrimSpace(*baseTierCHolderSnapshotPath) == "" {
		*baseTierCHolderSnapshotPath = resolveTierCDefaultPath(*configPath, "configs/tierc_holder_overrides.json")
	}

	logger := log.NewLogger(cfg.Platform.LogLevel, BuildMode)
	defer logger.Sync()

	ctx, cancel := setupSignalHandling()
	defer cancel()

	if *solanaReadiness {
		if err := runSolanaReadiness(ctx, cfg); err != nil {
			fmt.Fprintf(os.Stderr, "Solana readiness failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaQuoteReadiness {
		if err := runSolanaQuoteReadiness(ctx, *solanaQuoteInputMint, *solanaQuoteOutputMint, *solanaQuoteAmountRaw, *solanaQuoteSlippageBPS); err != nil {
			fmt.Fprintf(os.Stderr, "Solana quote readiness failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaSwapBuildReadiness {
		if err := runSolanaSwapBuildReadiness(ctx, cfg, *solanaSwapUserPublicKey, *solanaSwapInputMint, *solanaSwapOutputMint, *solanaSwapAmountRaw, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana swap build readiness failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaSwapSignReadiness {
		if err := runSolanaSwapSignReadiness(ctx, cfg, *solanaSwapUserPublicKey, *solanaSwapInputMint, *solanaSwapOutputMint, *solanaSwapAmountRaw, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana swap sign readiness failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaSwapCanary {
		if err := runSolanaSwapCanary(ctx, cfg, *solanaSwapUserPublicKey, *solanaSwapInputMint, *solanaSwapOutputMint, *solanaSwapAmountRaw, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana swap canary failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaFundingPlan {
		if err := runSolanaFundingPlan(ctx, cfg, *solanaSwapUserPublicKey, *solanaSwapInputMint, *solanaSwapAmountRaw, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports, *solanaFundingLedgerPositionID); err != nil {
			fmt.Fprintf(os.Stderr, "Solana funding plan failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPFundingPlan {
		if err := runSolanaLPFundingPlan(ctx, cfg, *solanaSwapUserPublicKey, *solanaLPTotalUSD, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports, *solanaFundingLedgerPositionID); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP funding plan failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPPreflight {
		if err := runSolanaLPPreflight(ctx, cfg, *solanaSwapUserPublicKey, *solanaLPTotalUSD, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP preflight failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaMeteoraLPPreflight {
		if err := runSolanaMeteoraLPPreflight(ctx, cfg, *solanaMeteoraLPPool, *solanaSwapUserPublicKey, *solanaLPTotalUSD, *solanaMeteoraLPRangePct, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana Meteora LP preflight failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaMeteoraLPBuildReadiness {
		if err := runSolanaMeteoraLPBuildReadiness(ctx, cfg, *solanaMeteoraLPPool, *solanaSwapUserPublicKey, *solanaLPTotalUSD, *solanaMeteoraLPRangePct, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana Meteora LP build readiness failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPClosePreflight {
		if err := runSolanaLPClosePreflight(ctx, cfg, *solanaSwapMaxPriorityLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP close preflight failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPPrefundCanary {
		if err := runSolanaLPPrefundCanary(ctx, cfg, *solanaSwapUserPublicKey, *solanaLPTotalUSD, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP prefund canary failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPOpenCanary {
		if err := runSolanaLPOpenCanary(ctx, cfg, *solanaSwapUserPublicKey, *solanaLPTotalUSD, *solanaQuoteSlippageBPS, *solanaSwapMaxPriorityLamports, *solanaFundingReserveLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP open canary failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPCloseCanary {
		if err := runSolanaLPCloseCanary(ctx, cfg, *solanaSwapMaxPriorityLamports); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP close canary failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaLPRealizedPnLReconcile {
		if err := runSolanaLPRealizedPnLReconcile(ctx, cfg, *canaryTokenID, *solanaQuoteSlippageBPS); err != nil {
			fmt.Fprintf(os.Stderr, "Solana LP realized PnL reconcile failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaDiscoveryReadiness {
		minTVL := domain.MustDecimal(*solanaDiscoveryMinTVL)
		minVol24h := domain.MustDecimal(*solanaDiscoveryMinVol24h)
		if err := runSolanaDiscoveryReadiness(ctx, cfg, minTVL, minVol24h, *solanaDiscoveryLimit); err != nil {
			fmt.Fprintf(os.Stderr, "Solana discovery readiness failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *solanaTierCDiscovery {
		minTVL := domain.MustDecimal(*solanaTierCMinTVL)
		maxTVL := domain.MustDecimal(*solanaTierCMaxTVL)
		minVol24h := domain.MustDecimal(*solanaTierCMinVol24h)
		minVolTVL := domain.MustDecimal(*solanaTierCMinVolTVL)
		if err := runSolanaTierCDiscovery(ctx, cfg, minTVL, maxTVL, minVol24h, minVolTVL, *solanaTierCLimit, *solanaTierCJSONOut, *solanaTierCIncludeRejects, *solanaTierCMajorOnly, *solanaTierCProtocol); err != nil {
			fmt.Fprintf(os.Stderr, "Solana Tier C discovery failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if strings.TrimSpace(*solanaTierCAuditPool) != "" {
		if err := runSolanaTierCAuditPool(ctx, cfg, *solanaTierCAuditPool, *solanaTierCJSONOut); err != nil {
			fmt.Fprintf(os.Stderr, "Solana Tier C pool audit failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if strings.TrimSpace(*solanaTierCDeepAuditWatchlist) != "" {
		if err := runSolanaTierCDeepAuditWatchlist(ctx, cfg, *solanaTierCDeepAuditWatchlist, *solanaTierCDeepAuditRounds, *solanaTierCDeepAuditIntervalSeconds, *solanaTierCJSONOut); err != nil {
			fmt.Fprintf(os.Stderr, "Solana Tier C deep audit watchlist failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *baseTierCDiscovery {
		minTVL := domain.MustDecimal(*baseTierCMinTVL)
		maxTVL := domain.MustDecimal(*baseTierCMaxTVL)
		minVol24h := domain.MustDecimal(*baseTierCMinVol24h)
		minVolTVL := domain.MustDecimal(*baseTierCMinVolTVL)
		minFeeAPR := domain.MustDecimal(*baseTierCMinFeeAPR)
		if err := runBaseTierCDiscovery(ctx, cfg, minTVL, maxTVL, minVol24h, minVolTVL, minFeeAPR, *baseTierCLimit, *baseTierCJSONOut, *baseTierCIncludeRejects); err != nil {
			fmt.Fprintf(os.Stderr, "Base Tier C discovery failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if strings.TrimSpace(*baseTierCAuditPool) != "" {
		if err := runBaseTierCAuditPool(ctx, cfg, *baseTierCAuditPool, *baseTierCJSONOut); err != nil {
			fmt.Fprintf(os.Stderr, "Base Tier C pool audit failed: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *baseTierCHolderSnapshotRefresh {
		if err := runBaseTierCHolderSnapshotRefresh(ctx, *baseTierCHolderSnapshotPath); err != nil {
			fmt.Fprintf(os.Stderr, "Base Tier C holder snapshot refresh failed: %v\n", err)
			os.Exit(1)
		}
		return
	}

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
	if *canaryPrepare {
		if BuildMode != "live" {
			fmt.Fprintln(os.Stderr, "Error: --canary-prepare requires a live build")
			os.Exit(1)
		}
		if err := runCanaryPrepare(ctx, cfg); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *canaryMint {
		if BuildMode != "live" {
			fmt.Fprintln(os.Stderr, "Error: --canary-mint requires a live build")
			os.Exit(1)
		}
		if err := runCanaryMint(ctx, cfg); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *canaryReconcileMint {
		if BuildMode != "live" {
			fmt.Fprintln(os.Stderr, "Error: --canary-reconcile-mint requires a live build")
			os.Exit(1)
		}
		if err := runCanaryMintReconcile(ctx, cfg, *canaryTxHash); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *canaryExitPreflight {
		if BuildMode != "live" {
			fmt.Fprintln(os.Stderr, "Error: --canary-exit-preflight requires a live build")
			os.Exit(1)
		}
		if err := runCanaryExitPreflight(ctx, cfg, *canaryTokenID); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if *canaryExit {
		if BuildMode != "live" {
			fmt.Fprintln(os.Stderr, "Error: --canary-exit requires a live build")
			os.Exit(1)
		}
		if err := runCanaryExit(ctx, cfg, *canaryTokenID); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}

	code := Run(ctx, logger, cfg)
	os.Exit(code)
}

func configureTierCPathEnv(configPath string) {
	if strings.TrimSpace(os.Getenv("LPBOT_TIERC_HOLDER_SNAPSHOT_PATH")) == "" {
		_ = os.Setenv("LPBOT_TIERC_HOLDER_SNAPSHOT_PATH", resolveTierCDefaultPath(configPath, "configs/tierc_holder_overrides.json"))
	}
	if strings.TrimSpace(os.Getenv("LPBOT_TIERC_NEGATIVE_SAMPLES_PATH")) == "" {
		_ = os.Setenv("LPBOT_TIERC_NEGATIVE_SAMPLES_PATH", resolveTierCDefaultPath(configPath, "configs/tierc_negative_samples.json"))
	}
}

func resolveTierCDefaultPath(configPath, relativeFromRepoRoot string) string {
	configPath = strings.TrimSpace(configPath)
	if configPath == "" {
		return relativeFromRepoRoot
	}
	absConfigPath, err := filepath.Abs(configPath)
	if err != nil {
		return relativeFromRepoRoot
	}
	baseDir := filepath.Dir(absConfigPath)
	if strings.EqualFold(filepath.Base(baseDir), "configs") {
		baseDir = filepath.Dir(baseDir)
	}
	return filepath.Join(baseDir, filepath.FromSlash(relativeFromRepoRoot))
}
