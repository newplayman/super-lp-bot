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
	CanaryEvents    []dashboardCanaryEvent     `json:"canary_events"`
	PositionMarks   []dashboardPositionMark    `json:"position_marks"`
	ExitPreflights  []dashboardExitPreflight   `json:"exit_preflights"`
	MarkSeries      []dashboardMarkPoint       `json:"mark_series"`
	LedgerSummary   []dashboardLedgerBucket    `json:"ledger_summary"`
	LedgerSeries    []dashboardLedgerPoint     `json:"ledger_series"`
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
	BaseCanary      dashboardBaseCanary        `json:"base_canary"`
	SolanaCanary    dashboardSolanaCanary      `json:"solana_canary"`
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

type dashboardBaseCanary struct {
	Broadcasts      int64  `json:"broadcasts"`
	Opened          int64  `json:"opened"`
	Closed          int64  `json:"closed"`
	TxBroadcasts    int64  `json:"tx_broadcasts"`
	PrepBroadcasts  int64  `json:"prep_broadcasts"`
	MintBroadcasts  int64  `json:"mint_broadcasts"`
	ExitBroadcasts  int64  `json:"exit_broadcasts"`
	ActivePositionID string `json:"active_position_id"`
	ActiveTokenID    string `json:"active_token_id"`
	ActiveStatus     string `json:"active_status"`
	ActiveHoldMinutes int64 `json:"active_hold_minutes"`
	ActiveNetPnLUSD  string `json:"active_net_pnl_usd"`
	ActiveFeeUSD     string `json:"active_fee_usd"`
	ActiveILUSD      string `json:"active_il_usd"`
	LastPositionID  string `json:"last_position_id"`
	LastTokenID     string `json:"last_token_id"`
	LastPoolID      string `json:"last_pool_id"`
	LastStatus      string `json:"last_status"`
	LastAmountUSD   string `json:"last_amount_usd"`
	LastHoldMinutes int64  `json:"last_hold_minutes"`
	LastNetPnLUSD   string `json:"last_net_pnl_usd"`
	LastFeeUSD      string `json:"last_fee_usd"`
	LastILUSD       string `json:"last_il_usd"`
	LastTxHash      string `json:"last_tx_hash"`
	LastClosedAt    int64  `json:"last_closed_at"`
}

type dashboardSolanaCanary struct {
	Broadcasts     int64  `json:"broadcasts"`
	LastTxHash     string `json:"last_tx_hash"`
	LastInputMint  string `json:"last_input_mint"`
	LastOutputMint string `json:"last_output_mint"`
	LastInputRaw   string `json:"last_input_raw"`
	LastOutputRaw  string `json:"last_output_raw"`
	SOLBalanceRaw  string `json:"sol_balance_raw"`
	USDCBalanceRaw string `json:"usdc_balance_raw"`
	LastCreatedAt  int64  `json:"last_created_at"`
}

type dashboardLiveReadiness struct {
	BuildMode             string                      `json:"build_mode"`
	LiveEnabled           bool                        `json:"live_enabled"`
	Canary                bool                        `json:"canary"`
	KillSwitch            bool                        `json:"kill_switch"`
	WalletAddress         string                      `json:"wallet_address"`
	WalletBalances        dashboardWalletBalances     `json:"wallet_balances"`
	FundingReady          bool                        `json:"funding_ready"`
	ApprovalsReady        bool                        `json:"approvals_ready"`
	AllowedChains         []string                    `json:"allowed_chains"`
	AllowedPoolsCount     int                         `json:"allowed_pools_count"`
	AllowedPoolChecks     []dashboardAllowedPoolCheck `json:"allowed_pool_checks"`
	MaxOrderUSD           float64                     `json:"max_order_usd"`
	DailyLossLimitUSD     float64                     `json:"daily_loss_limit_usd"`
	ExecutionBackend      string                      `json:"execution_backend"`
	ExecutionConfigured   bool                        `json:"execution_configured"`
	ExecutionBackendWired bool                        `json:"execution_backend_wired"`
	RPCPrimaryConfigured  bool                        `json:"rpc_primary_configured"`
	OKXAPIConfigured      bool                        `json:"okx_api_configured"`
	OKXProjectConfigured  bool                        `json:"okx_project_configured"`
	WalletBackend         string                      `json:"wallet_backend"`
	KeystorePath          string                      `json:"keystore_path"`
	KeystorePresent       bool                        `json:"keystore_present"`
	WalletPassphraseSet   bool                        `json:"wallet_passphrase_set"`
	NPMBaseAddress        string                      `json:"npm_base_address"`
	NPMBaseConfigured     bool                        `json:"npm_base_configured"`
	SizingPathReady       bool                        `json:"sizing_path_ready"`
	Ready                 bool                        `json:"ready"`
	Blockers              []string                    `json:"blockers"`
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

type dashboardAllowedPoolCheck struct {
	PoolID    string `json:"pool_id"`
	Token0    string `json:"token0"`
	Token1    string `json:"token1"`
	Fee       uint64 `json:"fee"`
	PairOK    bool   `json:"pair_ok"`
	CheckedAt string `json:"checked_at"`
	Error     string `json:"error,omitempty"`
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
	PoolID       string `json:"pool_id"`
	Chain        int    `json:"chain"`
	Protocol     string `json:"protocol"`
	Token0       string `json:"token0"`
	Token1       string `json:"token1"`
	FeeBPS       int    `json:"fee_bps"`
	Tier         string `json:"tier"`
	Score        string `json:"score"`
	UpdatedAt    int64  `json:"updated_at"`
	RiskEligible bool   `json:"risk_eligible"`
	RiskReason   string `json:"risk_reason"`
	TVLUSD       string `json:"tvl_usd"`
	Vol24hUSD    string `json:"vol24h_usd"`
}

type dashboardPosition struct {
	ID          string `json:"id"`
	TokenID     string `json:"token_id"`
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

type dashboardCanaryEvent struct {
	CreatedAt       int64  `json:"created_at"`
	Chain           string `json:"chain"`
	Command         string `json:"command"`
	Stage           string `json:"stage"`
	Status          string `json:"status"`
	PositionID      string `json:"position_id"`
	PoolID          string `json:"pool_id"`
	Wallet          string `json:"wallet"`
	TokenID         string `json:"token_id"`
	TxHash          string `json:"tx_hash"`
	AmountUSD       string `json:"amount_usd"`
	RequiredUSDCRaw string `json:"required_usdc_raw"`
	RequiredWETHRaw string `json:"required_weth_raw"`
	InputMint       string `json:"input_mint"`
	OutputMint      string `json:"output_mint"`
	InputAmountRaw  string `json:"input_amount_raw"`
	OutputAmountRaw string `json:"output_amount_raw"`
	SOLBalanceRaw   string `json:"sol_balance_raw"`
	USDCBalanceRaw  string `json:"usdc_balance_raw"`
	GasEstimate     uint64 `json:"gas_estimate"`
	Message         string `json:"message"`
	ErrorMsg        string `json:"error_msg"`
}

type dashboardScore struct {
	PoolID    string `json:"pool_id"`
	Chain     int    `json:"chain"`
	BlockTime int64  `json:"block_time"`
	ScoreJSON string `json:"score_json"`
}

type dashboardPositionMark struct {
	PositionID     string `json:"position_id"`
	TokenID        string `json:"token_id"`
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

type dashboardExitPreflight struct {
	PositionID       string `json:"position_id"`
	TokenID          string `json:"token_id"`
	PoolID           string `json:"pool_id"`
	Source           string `json:"source"`
	PrincipalUSD     string `json:"principal_usd"`
	FeeUSD           string `json:"fee_usd"`
	TotalUSD         string `json:"total_usd"`
	ILUSD            string `json:"il_usd"`
	NetPnLUSD        string `json:"net_pnl_usd"`
	DecreaseGas      uint64 `json:"decrease_gas"`
	CollectGas       uint64 `json:"collect_gas"`
	DecreaseTxHash   string `json:"decrease_tx_hash"`
	CollectTxHash    string `json:"collect_tx_hash"`
	ErrorMsg         string `json:"error_msg"`
	BroadcastEnabled bool   `json:"broadcast_enabled"`
	Command          string `json:"command"`
	UpdatedAt        int64  `json:"updated_at"`
	Status           string `json:"status"`
}

type dashboardMarkPoint struct {
	MarkTime     int64  `json:"mark_time"`
	ValuationUSD string `json:"valuation_usd"`
	NetPnLUSD    string `json:"net_pnl_usd"`
}

type dashboardLedgerBucket struct {
	Kind   string `json:"kind"`
	Amount string `json:"amount"`
}

type dashboardLedgerPoint struct {
	BlockTime int64  `json:"block_time"`
	FeeUSD    string `json:"fee_usd"`
	ILUSD     string `json:"il_usd"`
	NetPnLUSD string `json:"net_pnl_usd"`
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
		if token == "" || requestFromLoopback(r) {
			next(w, r)
			return
		}
		if dashboardTokenMatches(r, token) {
			http.SetCookie(w, &http.Cookie{
				Name:     "lpbot_dashboard_token",
				Value:    token,
				Path:     "/",
				MaxAge:   7 * 24 * 60 * 60,
				HttpOnly: true,
				SameSite: http.SameSiteLaxMode,
			})
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
	if strings.TrimPrefix(auth, "Bearer ") == token {
		return true
	}
	cookie, err := r.Cookie("lpbot_dashboard_token")
	return err == nil && cookie.Value == token
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
	if canary, err := dashboardLoadCanaryReadiness(ctx, app.rpcProviderForChain(domain.ChainBase)); err == nil {
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

	canaryEvents, err := queryDashboardCanaryEvents(ctx, db)
	if err != nil {
		snapshot.Warnings = append(snapshot.Warnings, fmt.Sprintf("dashboard canary events unavailable: %v", err))
	} else {
		snapshot.CanaryEvents = canaryEvents
	}
	if summary, err := queryDashboardSolanaCanary(ctx, db); err != nil {
		snapshot.Warnings = append(snapshot.Warnings, fmt.Sprintf("dashboard solana canary summary unavailable: %v", err))
	} else {
		snapshot.SolanaCanary = summary
	}

	positionMarks, err := queryDashboardPositionMarks(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.PositionMarks = positionMarks
	snapshot.BaseCanary = buildDashboardBaseCanary(snapshot.Positions, snapshot.ClosedPositions, snapshot.PositionMarks, snapshot.CanaryEvents)
	exitPreflights, err := queryDashboardExitPreflights(ctx, db)
	if err != nil {
		snapshot.Warnings = append(snapshot.Warnings, fmt.Sprintf("dashboard exit preflights unavailable: %v", err))
		exitPreflights = buildDashboardExitPreflights(positionMarks)
	}
	if len(exitPreflights) == 0 {
		exitPreflights = buildDashboardExitPreflights(positionMarks)
	}
	snapshot.ExitPreflights = exitPreflights

	markSeries, err := queryDashboardMarkSeries(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.MarkSeries = markSeries

	ledgerSummary, err := queryDashboardLedgerSummary(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.LedgerSummary = ledgerSummary

	ledgerSeries, err := queryDashboardLedgerSeries(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.LedgerSeries = ledgerSeries

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

func dashboardLoadCanaryReadiness(ctx context.Context, provider *rpc.RoundRobinProvider) (readiness dashboardLiveReadiness, err error) {
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
	balances, fundingReady, approvalsReady, balanceBlockers, balanceErr := dashboardCanaryWalletBalances(ctx, cfg, provider)
	readiness.WalletBalances = balances
	readiness.FundingReady = fundingReady
	readiness.ApprovalsReady = approvalsReady
	poolChecks, poolBlockers, poolErr := dashboardAllowedPoolChecks(ctx, cfg, provider)
	readiness.AllowedPoolChecks = poolChecks
	if balanceErr != nil {
		readiness.Blockers = append(readiness.Blockers, fmt.Sprintf("canary wallet balance check failed: %v", balanceErr))
		readiness.Ready = false
	} else if len(balanceBlockers) > 0 {
		readiness.Blockers = append(readiness.Blockers, balanceBlockers...)
		readiness.Ready = false
	}
	if poolErr != nil {
		readiness.Blockers = append(readiness.Blockers, fmt.Sprintf("canary allowed pool check failed: %v", poolErr))
		readiness.Ready = false
	} else if len(poolBlockers) > 0 {
		readiness.Blockers = append(readiness.Blockers, poolBlockers...)
		readiness.Ready = false
	}
	sort.Strings(readiness.Blockers)
	return readiness, nil
}

func dashboardCanaryWalletBalances(ctx context.Context, cfg *config.Config, provider *rpc.RoundRobinProvider) (dashboardWalletBalances, bool, bool, []string, error) {
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
	if provider == nil {
		return balances, false, false, nil, fmt.Errorf("base rpc provider not configured")
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
		blockers = append(blockers, "canary wallet has no WETH; WETH wrap is required before mint")
	}
	if npmAddress.IsZero() {
		blockers = append(blockers, "canary NPM spender address is invalid")
	}
	if usdcBalance.Sign() > 0 && usdcAllowance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no USDC allowance for NPM; exact approval is required before mint")
	}
	if wethBalance.Sign() > 0 && wethAllowance.Sign() <= 0 {
		blockers = append(blockers, "canary wallet has no WETH allowance for NPM; exact approval is required before mint")
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

func dashboardAllowedPoolChecks(ctx context.Context, cfg *config.Config, provider *rpc.RoundRobinProvider) ([]dashboardAllowedPoolCheck, []string, error) {
	if cfg == nil {
		return nil, nil, fmt.Errorf("canary config is nil")
	}
	if provider == nil {
		return nil, nil, fmt.Errorf("base rpc provider not configured")
	}

	queryCtx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	checks := make([]dashboardAllowedPoolCheck, 0, len(cfg.Live.AllowedPools))
	var blockers []string
	for _, poolID := range cfg.Live.AllowedPools {
		poolID = strings.TrimSpace(poolID)
		check := dashboardAllowedPoolCheck{
			PoolID:    poolID,
			CheckedAt: time.Now().UTC().Format(time.RFC3339),
		}
		poolAddress := parseAddressOrZero(poolID)
		if poolAddress.IsZero() {
			check.Error = "invalid pool address"
			blockers = append(blockers, fmt.Sprintf("canary allowed pool %s is invalid", poolID))
			checks = append(checks, check)
			continue
		}

		token0, err := dashboardPoolAddressMethod(queryCtx, provider, poolAddress, "0x0dfe1681")
		if err != nil {
			check.Error = fmt.Sprintf("token0: %v", err)
			blockers = append(blockers, fmt.Sprintf("canary allowed pool %s token0 check failed", poolID))
			checks = append(checks, check)
			continue
		}
		token1, err := dashboardPoolAddressMethod(queryCtx, provider, poolAddress, "0xd21220a7")
		if err != nil {
			check.Error = fmt.Sprintf("token1: %v", err)
			blockers = append(blockers, fmt.Sprintf("canary allowed pool %s token1 check failed", poolID))
			checks = append(checks, check)
			continue
		}
		fee, err := dashboardPoolUintMethod(queryCtx, provider, poolAddress, "0xddca3f43")
		if err != nil {
			check.Error = fmt.Sprintf("fee: %v", err)
			blockers = append(blockers, fmt.Sprintf("canary allowed pool %s fee check failed", poolID))
			checks = append(checks, check)
			continue
		}

		check.Token0 = token0.String()
		check.Token1 = token1.String()
		check.Fee = fee
		check.PairOK = isBaseWETHUSDCPair(token0, token1)
		if !check.PairOK {
			blockers = append(blockers, fmt.Sprintf("canary allowed pool %s is not Base WETH/USDC", poolID))
		}
		checks = append(checks, check)
	}
	return checks, blockers, nil
}

func dashboardPoolAddressMethod(ctx context.Context, provider *rpc.RoundRobinProvider, pool domain.Address, selector string) (domain.Address, error) {
	raw, err := provider.CallContract(ctx, ethereum.CallMsg{
		To:   ptrAddress(common.HexToAddress(pool.String())),
		Data: common.FromHex(selector),
	}, nil)
	if err != nil {
		return domain.Address{}, err
	}
	if len(raw) < 32 {
		return domain.Address{}, fmt.Errorf("short address response")
	}
	return domain.MustParseAddress(common.BytesToAddress(raw[len(raw)-20:]).Hex()), nil
}

func dashboardPoolUintMethod(ctx context.Context, provider *rpc.RoundRobinProvider, pool domain.Address, selector string) (uint64, error) {
	raw, err := provider.CallContract(ctx, ethereum.CallMsg{
		To:   ptrAddress(common.HexToAddress(pool.String())),
		Data: common.FromHex(selector),
	}, nil)
	if err != nil {
		return 0, err
	}
	if len(raw) == 0 {
		return 0, fmt.Errorf("empty uint response")
	}
	return new(big.Int).SetBytes(raw).Uint64(), nil
}

func isBaseWETHUSDCPair(token0, token1 domain.Address) bool {
	left := strings.ToLower(token0.String())
	right := strings.ToLower(token1.String())
	usdc := strings.ToLower(baseUSDCAddress)
	weth := strings.ToLower(baseWETHAddress)
	return (left == usdc && right == weth) || (left == weth && right == usdc)
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
	if err := ensureSolanaPoolRiskTable(ctx, db); err != nil {
		return nil, err
	}
	rows, err := db.QueryContext(ctx, `
		SELECT p.pool_id, p.chain, p.protocol, p.token0, p.token1, p.fee_bps,
		       COALESCE(p.tier, ''), COALESCE(p.last_score, ''), p.updated_at,
		       COALESCE(r.eligible, false), COALESCE(r.reason, ''), COALESCE(r.tvl_usd, '0'), COALESCE(r.vol24h_usd, '0')
		FROM pools p
		LEFT JOIN solana_pool_risk r ON r.pool_id = p.pool_id AND r.chain = p.chain
		ORDER BY p.updated_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard pools: %w", err)
	}
	defer rows.Close()

	var pools []dashboardPool
	for rows.Next() {
		var pool dashboardPool
		if err := rows.Scan(&pool.PoolID, &pool.Chain, &pool.Protocol, &pool.Token0, &pool.Token1, &pool.FeeBPS, &pool.Tier, &pool.Score, &pool.UpdatedAt, &pool.RiskEligible, &pool.RiskReason, &pool.TVLUSD, &pool.Vol24hUSD); err != nil {
			return nil, fmt.Errorf("scan dashboard pool: %w", err)
		}
		pools = append(pools, pool)
	}
	return pools, rows.Err()
}

func queryDashboardPositions(ctx context.Context, db *sql.DB) ([]dashboardPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, COALESCE(token_id, ''), pool_id, chain, status, COALESCE(tier, ''), amount_usd, opened_at, COALESCE(closed_at, 0)
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
		if err := rows.Scan(&pos.ID, &pos.TokenID, &pos.PoolID, &pos.Chain, &pos.Status, &pos.Tier, &pos.AmountUSD, &pos.OpenedAt, &pos.ClosedAt); err != nil {
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
			COALESCE(p.token_id, ''),
			p.pool_id,
			p.chain,
			p.status,
			COALESCE(p.tier, ''),
			p.amount_usd,
			p.opened_at,
			COALESCE(p.closed_at, 0),
			COALESCE(m.hold_minutes, 0),
			COALESCE((((ep.total_usd)::numeric - (p.amount_usd)::numeric))::text, m.net_pnl_usd, '0'),
			CASE
				WHEN COALESCE(ep.status, '') = 'closed' THEN 'real canary exit recorded'
				ELSE COALESCE(e.reason, '')
			END,
			CASE
				WHEN COALESCE(ep.status, '') = 'closed' THEN 'canary_exit'
				ELSE COALESCE(e.action, '')
			END
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
		LEFT JOIN (
			SELECT DISTINCT ON (token_id)
				token_id, total_usd, status
			FROM canary_exit_preflights
			WHERE COALESCE(token_id, '') <> ''
			ORDER BY token_id, checked_at DESC
		) ep ON ep.token_id = p.token_id
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
			&pos.TokenID,
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

func queryDashboardCanaryEvents(ctx context.Context, db *sql.DB) ([]dashboardCanaryEvent, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT created_at, COALESCE(chain, ''), command, stage, status, position_id, pool_id, wallet, token_id, tx_hash,
		       amount_usd, required_usdc_raw, required_weth_raw, COALESCE(input_mint, ''), COALESCE(output_mint, ''),
		       COALESCE(input_amount_raw, ''), COALESCE(output_amount_raw, ''), COALESCE(sol_balance_raw, ''), COALESCE(usdc_balance_raw, ''),
		       gas_estimate, message, error_msg
		FROM canary_events
		ORDER BY created_at DESC
		LIMIT 80
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard canary events: %w", err)
	}
	defer rows.Close()

	var events []dashboardCanaryEvent
	for rows.Next() {
		var event dashboardCanaryEvent
		if err := rows.Scan(
			&event.CreatedAt,
			&event.Chain,
			&event.Command,
			&event.Stage,
			&event.Status,
			&event.PositionID,
			&event.PoolID,
			&event.Wallet,
			&event.TokenID,
			&event.TxHash,
			&event.AmountUSD,
			&event.RequiredUSDCRaw,
			&event.RequiredWETHRaw,
			&event.InputMint,
			&event.OutputMint,
			&event.InputAmountRaw,
			&event.OutputAmountRaw,
			&event.SOLBalanceRaw,
			&event.USDCBalanceRaw,
			&event.GasEstimate,
			&event.Message,
			&event.ErrorMsg,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard canary event: %w", err)
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

func queryDashboardSolanaCanary(ctx context.Context, db *sql.DB) (dashboardSolanaCanary, error) {
	var summary dashboardSolanaCanary
	if err := db.QueryRowContext(ctx, `
		SELECT count(*)
		FROM canary_events
		WHERE chain = 'solana' AND stage = 'broadcast' AND status = 'ok'
	`).Scan(&summary.Broadcasts); err != nil {
		return summary, fmt.Errorf("query solana canary count: %w", err)
	}
	if err := db.QueryRowContext(ctx, `
		SELECT tx_hash, COALESCE(input_mint, ''), COALESCE(output_mint, ''),
		       COALESCE(input_amount_raw, ''), COALESCE(output_amount_raw, ''),
		       COALESCE(sol_balance_raw, ''), COALESCE(usdc_balance_raw, ''), created_at
		FROM canary_events
		WHERE chain = 'solana' AND stage = 'broadcast' AND status = 'ok'
		ORDER BY created_at DESC
		LIMIT 1
	`).Scan(
		&summary.LastTxHash,
		&summary.LastInputMint,
		&summary.LastOutputMint,
		&summary.LastInputRaw,
		&summary.LastOutputRaw,
		&summary.SOLBalanceRaw,
		&summary.USDCBalanceRaw,
		&summary.LastCreatedAt,
	); err != nil && err != sql.ErrNoRows {
		return summary, fmt.Errorf("query solana canary latest: %w", err)
	}
	return summary, nil
}

func buildDashboardBaseCanary(positions, closedPositions []dashboardPosition, marks []dashboardPositionMark, events []dashboardCanaryEvent) dashboardBaseCanary {
	var summary dashboardBaseCanary
	for _, pos := range positions {
		if pos.Chain != 1 || strings.TrimSpace(pos.TokenID) == "" {
			continue
		}
		summary.Opened++
		if strings.EqualFold(pos.Status, "closed") {
			summary.Closed++
		}
	}
	summary.Broadcasts = summary.Opened
	for _, event := range events {
		if !strings.EqualFold(event.Chain, "base") || strings.TrimSpace(event.TxHash) == "" || !strings.Contains(strings.ToLower(event.Stage), "broadcast") {
			continue
		}
		summary.TxBroadcasts++
		stage := strings.ToLower(event.Stage)
		switch {
		case strings.Contains(stage, "decrease_broadcast"), strings.Contains(stage, "collect_broadcast"):
			summary.ExitBroadcasts++
		case stage == "broadcast":
			summary.MintBroadcasts++
		default:
			summary.PrepBroadcasts++
		}
		if summary.LastTxHash == "" {
			summary.LastTxHash = event.TxHash
		}
	}
	for _, mark := range marks {
		if strings.TrimSpace(mark.TokenID) == "" || !strings.EqualFold(mark.Status, "open") {
			continue
		}
		summary.ActivePositionID = mark.PositionID
		summary.ActiveTokenID = mark.TokenID
		summary.ActiveStatus = mark.Status
		summary.ActiveHoldMinutes = mark.HoldMinutes
		summary.ActiveNetPnLUSD = mark.NetPnLUSD
		summary.ActiveFeeUSD = mark.FeeUSD
		summary.ActiveILUSD = mark.ILUSD
		break
	}
	if len(closedPositions) > 0 {
		pos := closedPositions[0]
		summary.LastPositionID = pos.ID
		summary.LastTokenID = pos.TokenID
		summary.LastPoolID = pos.PoolID
		summary.LastStatus = pos.Status
		summary.LastAmountUSD = pos.AmountUSD
		summary.LastHoldMinutes = pos.HoldMinutes
		summary.LastNetPnLUSD = pos.NetPnLUSD
		summary.LastClosedAt = pos.ClosedAt
	}
	for _, mark := range marks {
		if summary.LastPositionID == "" {
			break
		}
		if mark.PositionID != summary.LastPositionID {
			continue
		}
		summary.LastFeeUSD = mark.FeeUSD
		summary.LastILUSD = mark.ILUSD
		if strings.TrimSpace(summary.LastNetPnLUSD) == "" || summary.LastNetPnLUSD == "0" {
			summary.LastNetPnLUSD = mark.NetPnLUSD
		}
		break
	}
	return summary
}

func queryDashboardPositionMarks(ctx context.Context, db *sql.DB) ([]dashboardPositionMark, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT position_id, token_id, pool_id, status, tier, amount_usd, source, mark_time, hold_minutes,
		       valuation_usd, fee_usd, il_usd, net_pnl_usd,
		       current_tvl_usd, current_vol24h_usd, price_change_pct
		FROM (
			SELECT DISTINCT ON (position_id)
				m.position_id, COALESCE(p.token_id, '') AS token_id, m.pool_id, m.status, m.tier, m.amount_usd, m.source, m.mark_time, m.hold_minutes,
				valuation_usd, fee_usd, il_usd, net_pnl_usd,
				current_tvl_usd, current_vol24h_usd, price_change_pct
			FROM shadow_position_marks m
			LEFT JOIN positions p ON p.id = m.position_id
			ORDER BY m.position_id, m.mark_time DESC
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
			&mark.TokenID,
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

func buildDashboardExitPreflights(marks []dashboardPositionMark) []dashboardExitPreflight {
	preflights := make([]dashboardExitPreflight, 0)
	for _, mark := range marks {
		if strings.TrimSpace(mark.TokenID) == "" {
			continue
		}
		feeUSD := domain.MustDecimal(mark.FeeUSD)
		totalUSD := domain.MustDecimal(mark.ValuationUSD)
		principalUSD := totalUSD.Sub(feeUSD)
		status := "mark_estimate"
		if strings.Contains(mark.Source, "onchain_value") && strings.Contains(mark.Source, "onchain_fees") {
			status = "ready_preflight_cli"
		}
		preflights = append(preflights, dashboardExitPreflight{
			PositionID:       mark.PositionID,
			TokenID:          mark.TokenID,
			PoolID:           mark.PoolID,
			Source:           mark.Source,
			PrincipalUSD:     principalUSD.String(),
			FeeUSD:           mark.FeeUSD,
			TotalUSD:         mark.ValuationUSD,
			ILUSD:            mark.ILUSD,
			NetPnLUSD:        mark.NetPnLUSD,
			DecreaseGas:      0,
			CollectGas:       0,
			BroadcastEnabled: false,
			Command:          fmt.Sprintf("./bin/lpbot-live --config=configs/config.canary.toml --canary-exit-preflight --token-id=%s", mark.TokenID),
			UpdatedAt:        mark.MarkTime,
			Status:           status,
		})
	}
	return preflights
}

func queryDashboardExitPreflights(ctx context.Context, db *sql.DB) ([]dashboardExitPreflight, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT
			COALESCE(p.id, '') AS position_id,
			e.token_id,
			e.pool_id,
			'exit_preflight_db' AS source,
			e.principal_usd,
			e.fee_usd,
			e.total_usd,
			COALESCE(m.il_usd, '0') AS il_usd,
			(e.total_usd::numeric - COALESCE(p.amount_usd::numeric, 0))::text AS net_pnl_usd,
			e.decrease_gas,
			e.collect_gas,
			e.decrease_tx_hash,
			e.collect_tx_hash,
			e.error_msg,
			e.broadcast_enabled,
			('./bin/lpbot-live --config=configs/config.canary.toml --canary-exit-preflight --token-id=' || e.token_id) AS command,
			e.checked_at,
			e.status
		FROM canary_exit_preflights e
		LEFT JOIN positions p ON p.token_id = e.token_id
		LEFT JOIN LATERAL (
			SELECT il_usd
			FROM shadow_position_marks
			WHERE position_id = p.id
			ORDER BY mark_time DESC, id DESC
			LIMIT 1
		) m ON TRUE
		ORDER BY e.checked_at DESC
		LIMIT 20
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard exit preflights: %w", err)
	}
	defer rows.Close()

	preflights := make([]dashboardExitPreflight, 0)
	for rows.Next() {
		var item dashboardExitPreflight
		if err := rows.Scan(
			&item.PositionID,
			&item.TokenID,
			&item.PoolID,
			&item.Source,
			&item.PrincipalUSD,
			&item.FeeUSD,
			&item.TotalUSD,
			&item.ILUSD,
			&item.NetPnLUSD,
			&item.DecreaseGas,
			&item.CollectGas,
			&item.DecreaseTxHash,
			&item.CollectTxHash,
			&item.ErrorMsg,
			&item.BroadcastEnabled,
			&item.Command,
			&item.UpdatedAt,
			&item.Status,
		); err != nil {
			return nil, fmt.Errorf("scan dashboard exit preflight: %w", err)
		}
		preflights = append(preflights, item)
	}
	return preflights, rows.Err()
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

func queryDashboardLedgerSummary(ctx context.Context, db *sql.DB) ([]dashboardLedgerBucket, error) {
	rows, err := db.QueryContext(ctx, `
		WITH since AS (
			SELECT EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')::BIGINT AS ts
		)
		SELECT kind, COALESCE(SUM(amount::numeric), 0)::text
		FROM pnl_ledger, since
		WHERE block_time >= since.ts
		GROUP BY kind
		ORDER BY kind
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard ledger summary: %w", err)
	}
	defer rows.Close()

	var buckets []dashboardLedgerBucket
	for rows.Next() {
		var item dashboardLedgerBucket
		if err := rows.Scan(&item.Kind, &item.Amount); err != nil {
			return nil, fmt.Errorf("scan dashboard ledger summary: %w", err)
		}
		buckets = append(buckets, item)
	}
	return buckets, rows.Err()
}

func queryDashboardLedgerSeries(ctx context.Context, db *sql.DB) ([]dashboardLedgerPoint, error) {
	rows, err := db.QueryContext(ctx, `
		WITH grouped AS (
			SELECT
				block_time,
				COALESCE(SUM(CASE WHEN kind = 'fee' THEN amount::numeric ELSE 0 END), 0) AS fee_delta,
				COALESCE(SUM(CASE WHEN kind = 'il' THEN amount::numeric ELSE 0 END), 0) AS il_delta,
				COALESCE(SUM(amount::numeric), 0) AS net_delta
			FROM pnl_ledger
			GROUP BY block_time
		),
		running AS (
			SELECT
				block_time,
				SUM(fee_delta) OVER (ORDER BY block_time ASC) AS fee_usd,
				SUM(il_delta) OVER (ORDER BY block_time ASC) AS il_usd,
				SUM(net_delta) OVER (ORDER BY block_time ASC) AS net_pnl_usd
			FROM grouped
		)
		SELECT block_time, fee_usd::text, il_usd::text, net_pnl_usd::text
		FROM (
			SELECT *
			FROM running
			ORDER BY block_time DESC
			LIMIT 60
		) recent
		ORDER BY block_time ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard ledger series: %w", err)
	}
	defer rows.Close()

	var points []dashboardLedgerPoint
	for rows.Next() {
		var point dashboardLedgerPoint
		if err := rows.Scan(&point.BlockTime, &point.FeeUSD, &point.ILUSD, &point.NetPnLUSD); err != nil {
			return nil, fmt.Errorf("scan dashboard ledger point: %w", err)
		}
		points = append(points, point)
	}
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
