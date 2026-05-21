package main

import (
	"bufio"
	"context"
	"database/sql"
	_ "embed"
	"encoding/json"
	"fmt"
	"html/template"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

const (
	baseUSDCAddress = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
	baseWETHAddress = "0x4200000000000000000000000000000000000006"
)

//go:embed dashboard.html
var dashboardHTML string

type dbProvider interface {
	DB() *sql.DB
}

type dashboardSnapshot struct {
	GeneratedAt     string                     `json:"generated_at"`
	Version         string                     `json:"version"`
	Mode            string                     `json:"mode"`
	Commit          string                     `json:"commit"`
	Counts          dashboardCounts            `json:"counts"`
	LatestTick      dashboardTick              `json:"latest_tick"`
	LiveReadiness   dashboardLiveReadiness     `json:"live_readiness"`
	CanaryReadiness dashboardLiveReadiness     `json:"canary_readiness"`
	Pools           []dashboardPool            `json:"pools"`
	Positions       []dashboardPosition        `json:"positions"`
	ClosedPositions []dashboardPosition        `json:"closed_positions"`
	Transactions    []dashboardTransaction     `json:"transactions"`
	PositionMarks   []dashboardPositionMark    `json:"position_marks"`
	MarkSeries      []dashboardMarkPoint       `json:"mark_series"`
	ExitDecisions   []dashboardExitDecision    `json:"exit_decisions"`
	ExitActions     []dashboardExitAction      `json:"exit_actions"`
	RecentScores    []dashboardScore           `json:"recent_scores"`
	Decisions       []dashboardDecision        `json:"decisions"`
	Health          dashboardHealth            `json:"health"`
	ChainStages     []dashboardStageCount      `json:"chain_stages"`
	MarkSources     []dashboardStageCount      `json:"mark_sources"`
	RecentIssues    []dashboardRecentIssue     `json:"recent_issues"`
	StrategyAudit   []dashboardStrategyTick    `json:"strategy_audit"`
	StrategyQuality []dashboardStrategyQuality `json:"strategy_quality"`
	Warnings        []string                   `json:"warnings"`
}

type dashboardCounts struct {
	Pools        int64 `json:"pools"`
	Scores       int64 `json:"scores"`
	Positions    int64 `json:"positions"`
	Transactions int64 `json:"transactions"`
}

type dashboardTick struct {
	UpdatedAt       int64  `json:"updated_at"`
	UpdatedAtText   string `json:"updated_at_text"`
	ScannedEstimate int64  `json:"scanned_estimate"`
}

type dashboardHealth struct {
	LastMarkTime           int64  `json:"last_mark_time"`
	LastMarkTimeText       string `json:"last_mark_time_text"`
	LastMarkAgeSeconds     int64  `json:"last_mark_age_seconds"`
	LastMarkSource         string `json:"last_mark_source"`
	RecentStaleMarks       int64  `json:"recent_stale_marks"`
	RecentNonGeckoMarks    int64  `json:"recent_non_gecko_marks"`
	RecentChainFailures    int64  `json:"recent_chain_failures"`
	RecentPipelineFailures int64  `json:"recent_pipeline_failures"`
}

type dashboardLiveReadiness struct {
	BuildMode             string                  `json:"build_mode"`
	LiveEnabled           bool                    `json:"live_enabled"`
	Canary                bool                    `json:"canary"`
	KillSwitch            bool                    `json:"kill_switch"`
	WalletAddress         string                  `json:"wallet_address"`
	WalletBalances        dashboardWalletBalances `json:"wallet_balances"`
	FundingReady          bool                    `json:"funding_ready"`
	ApprovalsReady        bool                    `json:"approvals_ready"`
	AllowedChains         []string                `json:"allowed_chains"`
	AllowedPoolsCount     int                     `json:"allowed_pools_count"`
	MaxOrderUSD           float64                 `json:"max_order_usd"`
	DailyLossLimitUSD     float64                 `json:"daily_loss_limit_usd"`
	ExecutionBackend      string                  `json:"execution_backend"`
	ExecutionConfigured   bool                    `json:"execution_configured"`
	ExecutionBackendWired bool                    `json:"execution_backend_wired"`
	RPCPrimaryConfigured  bool                    `json:"rpc_primary_configured"`
	OKXAPIConfigured      bool                    `json:"okx_api_configured"`
	OKXProjectConfigured  bool                    `json:"okx_project_configured"`
	WalletBackend         string                  `json:"wallet_backend"`
	KeystorePath          string                  `json:"keystore_path"`
	KeystorePresent       bool                    `json:"keystore_present"`
	WalletPassphraseSet   bool                    `json:"wallet_passphrase_set"`
	NPMBaseAddress        string                  `json:"npm_base_address"`
	NPMBaseConfigured     bool                    `json:"npm_base_configured"`
	SizingPathReady       bool                    `json:"sizing_path_ready"`
	Ready                 bool                    `json:"ready"`
	Blockers              []string                `json:"blockers"`
}

type dashboardWalletBalances struct {
	Address       string `json:"address"`
	NPMSpender    string `json:"npm_spender"`
	ETH           string `json:"eth"`
	USDC          string `json:"usdc"`
	WETH          string `json:"weth"`
	USDCAllowance string `json:"usdc_allowance"`
	WETHAllowance string `json:"weth_allowance"`
	CheckedAt     string `json:"checked_at"`
	Error         string `json:"error,omitempty"`
}

type dashboardStageCount struct {
	Name  string `json:"name"`
	Count int64  `json:"count"`
}

type dashboardRecentIssue struct {
	TickTime int64  `json:"tick_time"`
	PoolID   string `json:"pool_id"`
	Stage    string `json:"stage"`
	Reason   string `json:"reason"`
	Action   string `json:"action"`
}

type dashboardStrategyTick struct {
	TickTime       int64 `json:"tick_time"`
	Scanned        int64 `json:"scanned"`
	Selected       int64 `json:"selected"`
	IntentOpen     int64 `json:"intent_open"`
	ChainOK        int64 `json:"chain_ok"`
	PipelineOK     int64 `json:"pipeline_ok"`
	OpenedOrReused int64 `json:"opened_or_reused"`
	Skipped        int64 `json:"skipped"`
}

type dashboardStrategyQuality struct {
	Segment       string  `json:"segment"`
	Bottleneck    string  `json:"bottleneck"`
	Count         int64   `json:"count"`
	AvgTotal      float64 `json:"avg_total"`
	AvgFeeAPR     float64 `json:"avg_fee_apr"`
	AvgTVL        float64 `json:"avg_tvl"`
	AvgVolume     float64 `json:"avg_volume"`
	AvgVolatility float64 `json:"avg_volatility"`
	AvgSecurity   float64 `json:"avg_security"`
	ExamplePoolID string  `json:"example_pool_id"`
	ExampleReason string  `json:"example_reason"`
}

type dashboardPool struct {
	PoolID    string `json:"pool_id"`
	Chain     int    `json:"chain"`
	Protocol  string `json:"protocol"`
	Token0    string `json:"token0"`
	Token1    string `json:"token1"`
	FeeBPS    int    `json:"fee_bps"`
	Tier      string `json:"tier"`
	Score     string `json:"score"`
	UpdatedAt int64  `json:"updated_at"`
}

type dashboardPosition struct {
	ID          string `json:"id"`
	PoolID      string `json:"pool_id"`
	Chain       int    `json:"chain"`
	Status      string `json:"status"`
	Tier        string `json:"tier"`
	AmountUSD   string `json:"amount_usd"`
	OpenedAt    int64  `json:"opened_at"`
	ClosedAt    int64  `json:"closed_at"`
	HoldMinutes int64  `json:"hold_minutes"`
	NetPnLUSD   string `json:"net_pnl_usd"`
	ExitReason  string `json:"exit_reason"`
	ExitAction  string `json:"exit_action"`
}

type dashboardTransaction struct {
	ID        string `json:"id"`
	Chain     string `json:"chain"`
	TxHash    string `json:"tx_hash"`
	Status    string `json:"status"`
	CreatedAt int64  `json:"created_at"`
	UpdatedAt int64  `json:"updated_at"`
}

type dashboardScore struct {
	PoolID    string `json:"pool_id"`
	Chain     int    `json:"chain"`
	BlockTime int64  `json:"block_time"`
	ScoreJSON string `json:"score_json"`
}

type dashboardPositionMark struct {
	PositionID     string `json:"position_id"`
	PoolID         string `json:"pool_id"`
	Status         string `json:"status"`
	Tier           string `json:"tier"`
	AmountUSD      string `json:"amount_usd"`
	Source         string `json:"source"`
	MarkTime       int64  `json:"mark_time"`
	HoldMinutes    int64  `json:"hold_minutes"`
	ValuationUSD   string `json:"valuation_usd"`
	FeeUSD         string `json:"fee_usd"`
	ILUSD          string `json:"il_usd"`
	NetPnLUSD      string `json:"net_pnl_usd"`
	CurrentTVLUSD  string `json:"current_tvl_usd"`
	CurrentVol24h  string `json:"current_vol24h_usd"`
	PriceChangePct string `json:"price_change_pct"`
}

type dashboardMarkPoint struct {
	MarkTime     int64  `json:"mark_time"`
	ValuationUSD string `json:"valuation_usd"`
	NetPnLUSD    string `json:"net_pnl_usd"`
}

type dashboardExitDecision struct {
	DecisionTime  int64  `json:"decision_time"`
	PositionID    string `json:"position_id"`
	PoolID        string `json:"pool_id"`
	Tier          string `json:"tier"`
	HoldMinutes   int64  `json:"hold_minutes"`
	CurrentTVLUSD string `json:"current_tvl_usd"`
	NetPnLUSD     string `json:"net_pnl_usd"`
	ILUSD         string `json:"il_usd"`
	WouldExit     bool   `json:"would_exit"`
	Reason        string `json:"reason"`
	Action        string `json:"action"`
}

type dashboardExitAction struct {
	DecisionTime int64  `json:"decision_time"`
	PositionID   string `json:"position_id"`
	PoolID       string `json:"pool_id"`
	Reason       string `json:"reason"`
	Action       string `json:"action"`
	TxHash       string `json:"tx_hash"`
	TxStatus     string `json:"tx_status"`
}

type dashboardDecision struct {
	TickTime        int64   `json:"tick_time"`
	PoolID          string  `json:"pool_id"`
	PoolKey         string  `json:"pool_key"`
	Protocol        string  `json:"protocol"`
	ScoreTotal      float64 `json:"score_total"`
	Selected        bool    `json:"selected"`
	SelectedRank    int     `json:"selected_rank"`
	SelectionReason string  `json:"selection_reason"`
	IntentOpen      bool    `json:"intent_open"`
	IntentReason    string  `json:"intent_reason"`
	ChainStage      string  `json:"chain_stage"`
	ChainReason     string  `json:"chain_reason"`
	PipelineStage   string  `json:"pipeline_stage"`
	PipelineOK      bool    `json:"pipeline_ok"`
	PipelineReason  string  `json:"pipeline_reason"`
	FinalAction     string  `json:"final_action"`
	PositionID      string  `json:"position_id"`
	TxHash          string  `json:"tx_hash"`
}

func (app *App) registerDashboardRoutes(mux *http.ServeMux) {
	mux.Handle("/web/", http.StripPrefix("/web/", http.FileServer(http.Dir("web"))))
	mux.HandleFunc("/web", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/web/", http.StatusFound)
	})
	mux.HandleFunc("/", app.dashboardAuth(app.redirectToWebDashboard))
	mux.HandleFunc("/dashboard", app.dashboardAuth(app.redirectToWebDashboard))
	mux.HandleFunc("/api/dashboard", app.dashboardAuth(app.handleDashboardAPI))
}

func (app *App) dashboardAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token := ""
		if app.config != nil {
			token = strings.TrimSpace(app.config.Platform.DashboardToken)
		}
		if token == "" || requestFromLoopback(r) || dashboardTokenMatches(r, token) {
			next(w, r)
			return
		}
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}
}

func requestFromLoopback(r *http.Request) bool {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func dashboardTokenMatches(r *http.Request, token string) bool {
	if r.URL.Query().Get("token") == token {
		return true
	}
	auth := r.Header.Get("Authorization")
	return strings.TrimPrefix(auth, "Bearer ") == token
}

func (app *App) handleDashboard(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	tmpl := template.Must(template.New("dashboard").Parse(dashboardHTML))
	_ = tmpl.Execute(w, map[string]string{
		"Version": Version,
		"Mode":    BuildMode,
		"Commit":  BuildCommit,
	})
}

func (app *App) redirectToWebDashboard(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" && r.URL.Path != "/dashboard" {
		http.NotFound(w, r)
		return
	}
	target := "/web/"
	if r.URL.RawQuery != "" {
		target += "?" + r.URL.RawQuery
	}
	http.Redirect(w, r, target, http.StatusFound)
}

func (app *App) handleDashboardAPI(w http.ResponseWriter, r *http.Request) {
	snapshot, err := app.dashboardSnapshot(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(snapshot)
}

func (app *App) dashboardSnapshot(ctx context.Context) (dashboardSnapshot, error) {
	snapshot := dashboardSnapshot{
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
		Version:     Version,
		Mode:        BuildMode,
		Commit:      BuildCommit,
	}
	if app.liveGate != nil {
		snapshot.LiveReadiness = app.liveGate.readiness()
	}
	if canary, err := dashboardLoadCanaryReadiness(ctx); err == nil {
		snapshot.CanaryReadiness = canary
	} else {
		snapshot.Warnings = append(snapshot.Warnings, fmt.Sprintf("canary readiness unavailable: %v", err))
	}
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		snapshot.Warnings = append(snapshot.Warnings, "dashboard requires postgres store with DB access")
		return snapshot, nil
	}
	db := provider.DB()
	if err := db.QueryRowContext(ctx, `
		SELECT
			(SELECT count(*) FROM pools),
			(SELECT count(*) FROM pool_score_history),
			(SELECT count(*) FROM positions),
			(SELECT count(*) FROM transactions)
	`).Scan(&snapshot.Counts.Pools, &snapshot.Counts.Scores, &snapshot.Counts.Positions, &snapshot.Counts.Transactions); err != nil {
		return snapshot, fmt.Errorf("query dashboard counts: %w", err)
	}

	_ = db.QueryRowContext(ctx, `
		SELECT COALESCE(max(block_time), 0), count(DISTINCT pool_id)
		FROM pool_score_history
		WHERE block_time = (SELECT max(block_time) FROM pool_score_history)
	`).Scan(&snapshot.LatestTick.UpdatedAt, &snapshot.LatestTick.ScannedEstimate)
	if snapshot.LatestTick.UpdatedAt > 0 {
		snapshot.LatestTick.UpdatedAtText = time.Unix(snapshot.LatestTick.UpdatedAt, 0).UTC().Format(time.RFC3339)
	}

	pools, err := queryDashboardPools(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Pools = pools

	positions, err := queryDashboardPositions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Positions = positions

	closedPositions, err := queryDashboardClosedPositions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.ClosedPositions = closedPositions

	txs, err := queryDashboardTransactions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Transactions = txs

	positionMarks, err := queryDashboardPositionMarks(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.PositionMarks = positionMarks

	markSeries, err := queryDashboardMarkSeries(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.MarkSeries = markSeries

	exitDecisions, err := queryDashboardExitDecisions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.ExitDecisions = exitDecisions

	exitActions, err := queryDashboardExitActions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.ExitActions = exitActions

	scores, err := queryDashboardScores(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.RecentScores = scores

	decisions, err := queryDashboardDecisions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Decisions = decisions

	health, err := queryDashboardHealth(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Health = health

	chainStages, err := queryDashboardChainStages(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.ChainStages = chainStages

	markSources, err := queryDashboardMarkSources(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.MarkSources = markSources

	recentIssues, err := queryDashboardRecentIssues(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.RecentIssues = recentIssues

	strategyAudit, err := queryDashboardStrategyAudit(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.StrategyAudit = strategyAudit

	strategyQuality, err := queryDashboardStrategyQuality(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.StrategyQuality = strategyQuality

	return snapshot, nil
}

func dashboardLoadCanaryReadiness(ctx context.Context) (readiness dashboardLiveReadiness, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			readiness = dashboardLiveReadiness{}
			err = fmt.Errorf("canary config panic: %v", recovered)
		}
	}()
	env, err := readDashboardEnvFiles(".env.canary", ".env.postgres", ".env.redis", ".env.dashboard")
	if err != nil {
		return dashboardLiveReadiness{}, err
	}
	cfg, err := config.LoadWithEnvMap(filepath.Clean("configs/config.canary.toml"), "live", env)
	if err != nil {
		return dashboardLiveReadiness{}, err
	}
	gate := newLiveSafetyGate("live", cfg)
	readiness = gate.readiness()
	balances, fundingReady, approvalsReady, balanceBlockers, balanceErr := dashboardCanaryWalletBalances(ctx, cfg)
	readiness.WalletBalances = balances
	readiness.FundingReady = fundingReady
	readiness.ApprovalsReady = approvalsReady
	if balanceErr != nil {
		readiness.Blockers = append(readiness.Blockers, fmt.Sprintf("canary wallet balance check failed: %v", balanceErr))
		readiness.Ready = false
	} else if len(balanceBlockers) > 0 {
		readiness.Blockers = append(readiness.Blockers, balanceBlockers...)
		readiness.Ready = false
	}
	sort.Strings(readiness.Blockers)
	return readiness, nil
}

func dashboardCanaryWalletBalances(ctx context.Context, cfg *config.Config) (dashboardWalletBalances, bool, bool, []string, error) {
	if cfg == nil {
		return dashboardWalletBalances{}, false, false, nil, fmt.Errorf("canary config is nil")
	}
	walletAddress := parseAddressOrZero(strings.TrimSpace(cfg.Live.WalletAddress))
	npmAddress := parseAddressOrZero(strings.TrimSpace(cfg.Execution.NPMBaseAddress))
	balances := dashboardWalletBalances{
		Address:    maskAddress(cfg.Live.WalletAddress),
		NPMSpender: maskAddress(cfg.Execution.NPMBaseAddress),
		CheckedAt:  time.Now().UTC().Format(time.RFC3339),
	}
	if walletAddress.IsZero() {
		return balances, false, false, []string{"canary wallet address is invalid"}, nil
	}

	endpoints := []string{cfg.Chains.Base.RPCPrimary}
	endpoints = append(endpoints, cfg.Chains.Base.RPCFallback...)
	endpoints = append(endpoints, rpc.BasePublicEndpoints...)
	provider, err := rpc.NewRoundRobinProvider(rpc.Config{
		ChainID:             domain.ChainBase,
		Endpoints:           endpoints,
		HealthCheckInterval: time.Minute,
		HealthCheckTimeout:  2 * time.Second,
	})
	if err != nil {
		return balances, false, false, nil, err
	}

	queryCtx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	ethBalance, err := provider.BalanceAt(queryCtx, walletAddress, nil)
	if err != nil {
		return balances, false, false, nil, fmt.Errorf("base eth balance: %w", err)
	}
	usdcBalance, err := dashboardERC20Balance(queryCtx, provider, baseUSDCAddress, walletAddress)
	if err != nil {
		return balances, false, false, nil, fmt.Errorf("base usdc balance: %w", err)
	}
	wethBalance, err := dashboardERC20Balance(queryCtx, provider, baseWETHAddress, walletAddress)
	if err != nil {
		return balances, false, false, nil, fmt.Errorf("base weth balance: %w", err)
	}
	usdcAllowance := big.NewInt(0)
	wethAllowance := big.NewInt(0)
	if !npmAddress.IsZero() {
		usdcAllowance, err = dashboardERC20Allowance(queryCtx, provider, baseUSDCAddress, walletAddress, npmAddress)
		if err != nil {
			return balances, false, false, nil, fmt.Errorf("base usdc allowance: %w", err)
		}
		wethAllowance, err = dashboardERC20Allowance(queryCtx, provider, baseWETHAddress, walletAddress, npmAddress)
		if err != nil {
			return balances, false, false, nil, fmt.Errorf("base weth allowance: %w", err)
		}
	}

	balances.ETH = formatTokenBalance(ethBalance, 18)
	balances.USDC = formatTokenBalance(usdcBalance, 6)
	balances.WETH = formatTokenBalance(wethBalance, 18)
	balances.USDCAllowance = formatTokenBalance(usdcAllowance, 6)
	balances.WETHAllowance = formatTokenBalance(wethAllowance, 18)

	var blockers []string
	if ethBalance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no Base ETH for gas")
	}
	if usdcBalance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no Base USDC for the WETH/USDC test")
	}
	if wethBalance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no WETH; automated swap/pairing path is not implemented")
	}
	if npmAddress.IsZero() {
		blockers = append(blockers, "canary NPM spender address is invalid")
	}
	if usdcBalance.Sign() > 0 && usdcAllowance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no USDC allowance for NPM; approval path is not wired")
	}
	if wethBalance.Sign() > 0 && wethAllowance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no WETH allowance for NPM; approval path is not wired")
	}
	fundingReady := ethBalance.Sign() > 0 && usdcBalance.Sign() > 0 && wethBalance.Sign() > 0
	approvalsReady := !npmAddress.IsZero() && usdcAllowance.Sign() > 0 && (wethBalance.Sign() <= 0 || wethAllowance.Sign() > 0)
	return balances, fundingReady, approvalsReady, blockers, nil
}

func dashboardERC20Balance(ctx context.Context, provider *rpc.RoundRobinProvider, token string, owner domain.Address) (*big.Int, error) {
	selector := common.FromHex("0x70a08231")
	ownerBytes := common.LeftPadBytes(common.HexToAddress(owner.String()).Bytes(), 32)
	data := append(selector, ownerBytes...)
	raw, err := provider.CallContract(ctx, ethereum.CallMsg{
		To:   ptrAddress(common.HexToAddress(token)),
		Data: data,
	}, nil)
	if err != nil {
		return nil, err
	}
	return new(big.Int).SetBytes(raw), nil
}

func dashboardERC20Allowance(ctx context.Context, provider *rpc.RoundRobinProvider, token string, owner, spender domain.Address) (*big.Int, error) {
	selector := common.FromHex("0xdd62ed3e")
	ownerBytes := common.LeftPadBytes(common.HexToAddress(owner.String()).Bytes(), 32)
	spenderBytes := common.LeftPadBytes(common.HexToAddress(spender.String()).Bytes(), 32)
	data := append(selector, ownerBytes...)
	data = append(data, spenderBytes...)
	raw, err := provider.CallContract(ctx, ethereum.CallMsg{
		To:   ptrAddress(common.HexToAddress(token)),
		Data: data,
	}, nil)
	if err != nil {
		return nil, err
	}
	return new(big.Int).SetBytes(raw), nil
}

func ptrAddress(value common.Address) *common.Address {
	return &value
}

func formatTokenBalance(value *big.Int, decimals int) string {
	if value == nil {
		return "0"
	}
	rat := new(big.Rat).SetFrac(value, new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(decimals)), nil))
	return rat.FloatString(minInt(decimals, 8))
}

func readDashboardEnvFiles(paths ...string) (map[string]string, error) {
	values := make(map[string]string)
	seenAny := false
	for _, path := range paths {
		file, err := os.Open(filepath.Clean(path))
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, err
		}
		seenAny = true
		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			key, value, ok := strings.Cut(line, "=")
			if !ok {
				continue
			}
			values[strings.TrimSpace(key)] = strings.TrimSpace(value)
		}
		if err := scanner.Err(); err != nil {
			_ = file.Close()
			return nil, err
		}
		_ = file.Close()
	}
	if !seenAny {
		return nil, fmt.Errorf("no canary env files found")
	}
	return values, nil
}

func queryDashboardPools(ctx context.Context, db *sql.DB) ([]dashboardPool, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT pool_id, chain, protocol, token0, token1, fee_bps,
		       COALESCE(tier, ''), COALESCE(last_score, ''), updated_at
		FROM pools
		ORDER BY updated_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard pools: %w", err)
	}
	defer rows.Close()

	var pools []dashboardPool
	for rows.Next() {
		var pool dashboardPool
		if err := rows.Scan(&pool.PoolID, &pool.Chain, &pool.Protocol, &pool.Token0, &pool.Token1, &pool.FeeBPS, &pool.Tier, &pool.Score, &pool.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan dashboard pool: %w", err)
		}
		pools = append(pools, pool)
	}
	return pools, rows.Err()
}

func queryDashboardPositions(ctx context.Context, db *sql.DB) ([]dashboardPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, pool_id, chain, status, COALESCE(tier, ''), amount_usd, opened_at, COALESCE(closed_at, 0)
		FROM positions
		ORDER BY opened_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard positions: %w", err)
	}
	defer rows.Close()

	var positions []dashboardPosition
	for rows.Next() {
		var pos dashboardPosition
		if err := rows.Scan(&pos.ID, &pos.PoolID, &pos.Chain, &pos.Status, &pos.Tier, &pos.AmountUSD, &pos.OpenedAt, &pos.ClosedAt); err != nil {
			return nil, fmt.Errorf("scan dashboard position: %w", err)
		}
		positions = append(positions, pos)
	}
	return positions, rows.Err()
}

func queryDashboardClosedPositions(ctx context.Context, db *sql.DB) ([]dashboardPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT
			p.id,
			p.pool_id,
			p.chain,
			p.status,
			COALESCE(p.tier, ''),
			p.amount_usd,
			p.opened_at,
			COALESCE(p.closed_at, 0),
			COALESCE(m.hold_minutes, 0),
			COALESCE(m.net_pnl_usd, '0'),
			COALESCE(e.reason, ''),
			COALESCE(e.action, '')
		FROM positions p
		LEFT JOIN (
			SELECT DISTINCT ON (position_id)
				position_id, hold_minutes, net_pnl_usd
			FROM shadow_position_marks
			ORDER BY position_id, mark_time DESC
		) m ON m.position_id = p.id
		LEFT JOIN (
			SELECT DISTINCT ON (position_id)
				position_id, reason, action
			FROM shadow_exit_decisions
			WHERE would_exit = TRUE
			ORDER BY position_id, decision_time DESC
		) e ON e.position_id = p.id
		WHERE p.status = 'closed'
		ORDER BY p.closed_at DESC, p.opened_at DESC
		LIMIT 30
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard closed positions: %w", err)
	}
	defer rows.Close()

	var positions []dashboardPosition
	for rows.Next() {
		var pos dashboardPosition
		if err := rows.Scan(
			&pos.ID,
			&pos.PoolID,
			&pos.Chain,
			&pos.Status,
			&pos.Tier,
			&pos.AmountUSD,
			&pos.OpenedAt,
			&pos.ClosedAt,
			&pos.HoldMinutes,
			&pos.NetPnLUSD,
			&pos.ExitReason,
			&pos.ExitAction,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard closed position: %w", err)
		}
		positions = append(positions, pos)
	}
	return positions, rows.Err()
}

func queryDashboardTransactions(ctx context.Context, db *sql.DB) ([]dashboardTransaction, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, chain, tx_hash, status, created_at, updated_at
		FROM transactions
		ORDER BY created_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard transactions: %w", err)
	}
	defer rows.Close()

	var txs []dashboardTransaction
	for rows.Next() {
		var tx dashboardTransaction
		if err := rows.Scan(&tx.ID, &tx.Chain, &tx.TxHash, &tx.Status, &tx.CreatedAt, &tx.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan dashboard transaction: %w", err)
		}
		txs = append(txs, tx)
	}
	return txs, rows.Err()
}

func queryDashboardPositionMarks(ctx context.Context, db *sql.DB) ([]dashboardPositionMark, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT position_id, pool_id, status, tier, amount_usd, source, mark_time, hold_minutes,
		       valuation_usd, fee_usd, il_usd, net_pnl_usd,
		       current_tvl_usd, current_vol24h_usd, price_change_pct
		FROM (
			SELECT DISTINCT ON (position_id)
				position_id, pool_id, status, tier, amount_usd, source, mark_time, hold_minutes,
				valuation_usd, fee_usd, il_usd, net_pnl_usd,
				current_tvl_usd, current_vol24h_usd, price_change_pct
			FROM shadow_position_marks
			ORDER BY position_id, mark_time DESC
		) latest
		ORDER BY mark_time DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard position marks: %w", err)
	}
	defer rows.Close()

	var marks []dashboardPositionMark
	for rows.Next() {
		var mark dashboardPositionMark
		if err := rows.Scan(
			&mark.PositionID,
			&mark.PoolID,
			&mark.Status,
			&mark.Tier,
			&mark.AmountUSD,
			&mark.Source,
			&mark.MarkTime,
			&mark.HoldMinutes,
			&mark.ValuationUSD,
			&mark.FeeUSD,
			&mark.ILUSD,
			&mark.NetPnLUSD,
			&mark.CurrentTVLUSD,
			&mark.CurrentVol24h,
			&mark.PriceChangePct,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard position mark: %w", err)
		}
		marks = append(marks, mark)
	}
	return marks, rows.Err()
}

func queryDashboardExitDecisions(ctx context.Context, db *sql.DB) ([]dashboardExitDecision, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT decision_time, position_id, pool_id, tier, hold_minutes,
		       current_tvl_usd, net_pnl_usd, il_usd, would_exit, reason, action
		FROM (
			SELECT DISTINCT ON (position_id)
				decision_time, position_id, pool_id, tier, hold_minutes,
				current_tvl_usd, net_pnl_usd, il_usd, would_exit, reason, action
			FROM shadow_exit_decisions
			ORDER BY position_id, decision_time DESC
		) latest
		ORDER BY decision_time DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard exit decisions: %w", err)
	}
	defer rows.Close()

	var decisions []dashboardExitDecision
	for rows.Next() {
		var decision dashboardExitDecision
		if err := rows.Scan(
			&decision.DecisionTime,
			&decision.PositionID,
			&decision.PoolID,
			&decision.Tier,
			&decision.HoldMinutes,
			&decision.CurrentTVLUSD,
			&decision.NetPnLUSD,
			&decision.ILUSD,
			&decision.WouldExit,
			&decision.Reason,
			&decision.Action,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard exit decision: %w", err)
		}
		decisions = append(decisions, decision)
	}
	return decisions, rows.Err()
}

func queryDashboardExitActions(ctx context.Context, db *sql.DB) ([]dashboardExitAction, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT decision_time, position_id, pool_id, reason, action, tx_hash, tx_status
		FROM shadow_exit_actions
		ORDER BY id DESC
		LIMIT 30
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard exit actions: %w", err)
	}
	defer rows.Close()

	var actions []dashboardExitAction
	for rows.Next() {
		var action dashboardExitAction
		if err := rows.Scan(
			&action.DecisionTime,
			&action.PositionID,
			&action.PoolID,
			&action.Reason,
			&action.Action,
			&action.TxHash,
			&action.TxStatus,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard exit action: %w", err)
		}
		actions = append(actions, action)
	}
	return actions, rows.Err()
}

func queryDashboardMarkSeries(ctx context.Context, db *sql.DB) ([]dashboardMarkPoint, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT mark_time,
		       COALESCE(sum(valuation_usd::numeric), 0)::text AS valuation_usd,
		       COALESCE(sum(net_pnl_usd::numeric), 0)::text AS net_pnl_usd
		FROM shadow_position_marks
		GROUP BY mark_time
		ORDER BY mark_time DESC
		LIMIT 60
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard mark series: %w", err)
	}
	defer rows.Close()

	var points []dashboardMarkPoint
	for rows.Next() {
		var point dashboardMarkPoint
		if err := rows.Scan(&point.MarkTime, &point.ValuationUSD, &point.NetPnLUSD); err != nil {
			return nil, fmt.Errorf("scan dashboard mark point: %w", err)
		}
		points = append(points, point)
	}
	sort.Slice(points, func(i, j int) bool {
		return points[i].MarkTime < points[j].MarkTime
	})
	return points, rows.Err()
}

func queryDashboardScores(ctx context.Context, db *sql.DB) ([]dashboardScore, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT pool_id, chain, block_time, score_json
		FROM pool_score_history
		ORDER BY id DESC
		LIMIT 20
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard scores: %w", err)
	}
	defer rows.Close()

	var scores []dashboardScore
	for rows.Next() {
		var score dashboardScore
		if err := rows.Scan(&score.PoolID, &score.Chain, &score.BlockTime, &score.ScoreJSON); err != nil {
			return nil, fmt.Errorf("scan dashboard score: %w", err)
		}
		scores = append(scores, score)
	}
	sort.Slice(scores, func(i, j int) bool {
		return scores[i].BlockTime > scores[j].BlockTime
	})
	return scores, rows.Err()
}

func queryDashboardDecisions(ctx context.Context, db *sql.DB) ([]dashboardDecision, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT tick_time, pool_id, pool_key, protocol, score_total,
		       selected, COALESCE(selected_rank, 0), selection_reason,
		       intent_open, intent_reason, chain_stage, chain_reason,
		       pipeline_stage, pipeline_ok,
		       pipeline_reason, final_action,
		       COALESCE(position_id, ''), COALESCE(tx_hash, '')
		FROM shadow_decision_trace
		ORDER BY id DESC
		LIMIT 30
	`)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("query dashboard decisions: %w", err)
	}
	defer rows.Close()

	var decisions []dashboardDecision
	for rows.Next() {
		var decision dashboardDecision
		if err := rows.Scan(
			&decision.TickTime,
			&decision.PoolID,
			&decision.PoolKey,
			&decision.Protocol,
			&decision.ScoreTotal,
			&decision.Selected,
			&decision.SelectedRank,
			&decision.SelectionReason,
			&decision.IntentOpen,
			&decision.IntentReason,
			&decision.ChainStage,
			&decision.ChainReason,
			&decision.PipelineStage,
			&decision.PipelineOK,
			&decision.PipelineReason,
			&decision.FinalAction,
			&decision.PositionID,
			&decision.TxHash,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard decision: %w", err)
		}
		decisions = append(decisions, decision)
	}
	return decisions, rows.Err()
}

func queryDashboardHealth(ctx context.Context, db *sql.DB) (dashboardHealth, error) {
	var health dashboardHealth
	since := time.Now().Add(-30 * time.Minute).Unix()
	if err := db.QueryRowContext(ctx, `
		SELECT
			COALESCE((SELECT mark_time FROM shadow_position_marks ORDER BY mark_time DESC, id DESC LIMIT 1), 0),
			COALESCE((SELECT source FROM shadow_position_marks ORDER BY mark_time DESC, id DESC LIMIT 1), ''),
			(SELECT count(*) FROM shadow_position_marks WHERE mark_time >= $1 AND source LIKE '%stale%'),
			(SELECT count(*) FROM shadow_position_marks WHERE mark_time >= $1 AND source <> '' AND source <> 'geckoterminal'),
			(SELECT count(*) FROM shadow_decision_trace WHERE tick_time >= $1 AND chain_stage <> '' AND chain_stage NOT LIKE 'chain_%validated%'),
			(SELECT count(*) FROM shadow_decision_trace WHERE tick_time >= $1 AND pipeline_stage <> '' AND pipeline_ok = FALSE)
	`, since).Scan(
		&health.LastMarkTime,
		&health.LastMarkSource,
		&health.RecentStaleMarks,
		&health.RecentNonGeckoMarks,
		&health.RecentChainFailures,
		&health.RecentPipelineFailures,
	); err != nil {
		return health, fmt.Errorf("query dashboard health: %w", err)
	}
	if health.LastMarkTime > 0 {
		health.LastMarkTimeText = time.Unix(health.LastMarkTime, 0).UTC().Format(time.RFC3339)
		health.LastMarkAgeSeconds = time.Now().Unix() - health.LastMarkTime
	}
	return health, nil
}

func queryDashboardChainStages(ctx context.Context, db *sql.DB) ([]dashboardStageCount, error) {
	return queryDashboardStageCounts(ctx, db, `
		SELECT COALESCE(NULLIF(chain_stage, ''), 'blank') AS name, count(*)
		FROM (
			SELECT chain_stage
			FROM shadow_decision_trace
			ORDER BY id DESC
			LIMIT 300
		) recent
		GROUP BY name
		ORDER BY count(*) DESC, name
	`)
}

func queryDashboardMarkSources(ctx context.Context, db *sql.DB) ([]dashboardStageCount, error) {
	return queryDashboardStageCounts(ctx, db, `
		SELECT COALESCE(NULLIF(source, ''), 'blank') AS name, count(*)
		FROM (
			SELECT source
			FROM shadow_position_marks
			ORDER BY id DESC
			LIMIT 100
		) recent
		GROUP BY name
		ORDER BY count(*) DESC, name
	`)
}

func queryDashboardStageCounts(ctx context.Context, db *sql.DB, query string) ([]dashboardStageCount, error) {
	rows, err := db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query dashboard stage counts: %w", err)
	}
	defer rows.Close()

	var counts []dashboardStageCount
	for rows.Next() {
		var count dashboardStageCount
		if err := rows.Scan(&count.Name, &count.Count); err != nil {
			return nil, fmt.Errorf("scan dashboard stage count: %w", err)
		}
		counts = append(counts, count)
	}
	return counts, rows.Err()
}

func queryDashboardRecentIssues(ctx context.Context, db *sql.DB) ([]dashboardRecentIssue, error) {
	since := time.Now().Add(-30 * time.Minute).Unix()
	rows, err := db.QueryContext(ctx, `
		SELECT tick_time, pool_id,
		       COALESCE(NULLIF(chain_stage, ''), NULLIF(pipeline_stage, ''), 'unknown') AS stage,
		       COALESCE(NULLIF(chain_reason, ''), NULLIF(pipeline_reason, ''), selection_reason, '') AS reason,
		       final_action
		FROM shadow_decision_trace
		WHERE tick_time >= $1
		  AND (
			(chain_stage <> '' AND chain_stage NOT LIKE 'chain_%validated%')
			OR (pipeline_stage <> '' AND pipeline_ok = FALSE)
		  )
		ORDER BY id DESC
		LIMIT 20
	`, since)
	if err != nil {
		return nil, fmt.Errorf("query dashboard recent issues: %w", err)
	}
	defer rows.Close()

	var issues []dashboardRecentIssue
	for rows.Next() {
		var issue dashboardRecentIssue
		if err := rows.Scan(&issue.TickTime, &issue.PoolID, &issue.Stage, &issue.Reason, &issue.Action); err != nil {
			return nil, fmt.Errorf("scan dashboard recent issue: %w", err)
		}
		issues = append(issues, issue)
	}
	return issues, rows.Err()
}

func queryDashboardStrategyAudit(ctx context.Context, db *sql.DB) ([]dashboardStrategyTick, error) {
	rows, err := db.QueryContext(ctx, `
		WITH recent_ticks AS (
			SELECT DISTINCT tick_time
			FROM shadow_decision_trace
			ORDER BY tick_time DESC
			LIMIT 12
		)
		SELECT d.tick_time,
		       count(*) AS scanned,
		       count(*) FILTER (WHERE selected) AS selected,
		       count(*) FILTER (WHERE intent_open) AS intent_open,
		       count(*) FILTER (WHERE chain_stage LIKE 'chain_%validated%') AS chain_ok,
		       count(*) FILTER (WHERE pipeline_ok) AS pipeline_ok,
		       count(*) FILTER (WHERE final_action IN ('open_shadow_position', 'reuse_shadow_position')) AS opened_or_reused,
		       count(*) FILTER (WHERE final_action = 'skip') AS skipped
		FROM shadow_decision_trace d
		JOIN recent_ticks r ON r.tick_time = d.tick_time
		GROUP BY d.tick_time
		ORDER BY d.tick_time DESC
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard strategy audit: %w", err)
	}
	defer rows.Close()

	var ticks []dashboardStrategyTick
	for rows.Next() {
		var tick dashboardStrategyTick
		if err := rows.Scan(
			&tick.TickTime,
			&tick.Scanned,
			&tick.Selected,
			&tick.IntentOpen,
			&tick.ChainOK,
			&tick.PipelineOK,
			&tick.OpenedOrReused,
			&tick.Skipped,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard strategy audit: %w", err)
		}
		ticks = append(ticks, tick)
	}
	return ticks, rows.Err()
}

func queryDashboardStrategyQuality(ctx context.Context, db *sql.DB) ([]dashboardStrategyQuality, error) {
	rows, err := db.QueryContext(ctx, `
		WITH latest AS (
			SELECT max(tick_time) AS tick_time
			FROM shadow_decision_trace
		),
		enriched AS (
			SELECT
				d.pool_id,
				d.score_total,
				d.selected,
				d.intent_open,
				d.pipeline_ok,
				d.selection_reason,
				d.intent_reason,
				d.pipeline_reason,
				COALESCE((d.score_json::jsonb ->> 'FeeAPRScore')::double precision, 0) AS fee_apr,
				COALESCE((d.score_json::jsonb ->> 'TvlScore')::double precision, 0) AS tvl,
				COALESCE((d.score_json::jsonb ->> 'VolScore')::double precision, 0) AS volume,
				COALESCE((d.score_json::jsonb ->> 'VolatilityScore')::double precision, 0) AS volatility,
				COALESCE((d.score_json::jsonb ->> 'SecurityScore')::double precision, 0) AS security
			FROM shadow_decision_trace d
			JOIN latest l ON l.tick_time = d.tick_time
		),
		classified AS (
			SELECT *,
				CASE
					WHEN pipeline_ok THEN 'passed_pipeline'
					WHEN selected AND intent_open THEN 'intent_pipeline_blocked'
					WHEN selected AND NOT intent_open THEN 'selected_below_open_threshold'
					WHEN NOT selected AND score_total >= 60 THEN 'not_selected_top_cutoff'
					WHEN NOT selected THEN 'not_selected_score_lt_60'
					ELSE 'other'
				END AS segment,
				CASE least(fee_apr, tvl, volume, volatility, security)
					WHEN fee_apr THEN 'fee_apr'
					WHEN tvl THEN 'tvl'
					WHEN volume THEN 'volume'
					WHEN volatility THEN 'volatility'
					ELSE 'security'
				END AS bottleneck
			FROM enriched
		),
		ranked AS (
			SELECT *,
				row_number() OVER (PARTITION BY segment, bottleneck ORDER BY score_total DESC, pool_id) AS rn
			FROM classified
		)
		SELECT
			segment,
			bottleneck,
			count(*) AS count,
			avg(score_total) AS avg_total,
			avg(fee_apr) AS avg_fee_apr,
			avg(tvl) AS avg_tvl,
			avg(volume) AS avg_volume,
			avg(volatility) AS avg_volatility,
			avg(security) AS avg_security,
			COALESCE(max(pool_id) FILTER (WHERE rn = 1), '') AS example_pool_id,
			COALESCE(max(NULLIF(coalesce(pipeline_reason, intent_reason, selection_reason), '')) FILTER (WHERE rn = 1), '') AS example_reason
		FROM ranked
		GROUP BY segment, bottleneck
		ORDER BY
			CASE segment
				WHEN 'passed_pipeline' THEN 1
				WHEN 'intent_pipeline_blocked' THEN 2
				WHEN 'selected_below_open_threshold' THEN 3
				WHEN 'not_selected_top_cutoff' THEN 4
				WHEN 'not_selected_score_lt_60' THEN 5
				ELSE 6
			END,
			count(*) DESC,
			bottleneck
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard strategy quality: %w", err)
	}
	defer rows.Close()

	var quality []dashboardStrategyQuality
	for rows.Next() {
		var item dashboardStrategyQuality
		if err := rows.Scan(
			&item.Segment,
			&item.Bottleneck,
			&item.Count,
			&item.AvgTotal,
			&item.AvgFeeAPR,
			&item.AvgTVL,
			&item.AvgVolume,
			&item.AvgVolatility,
			&item.AvgSecurity,
			&item.ExamplePoolID,
			&item.ExampleReason,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard strategy quality: %w", err)
		}
		quality = append(quality, item)
	}
	return quality, rows.Err()
}
