package main

import (
	"context"
	"database/sql"
	_ "embed"
	"encoding/json"
	"fmt"
	"html/template"
	"net"
	"net/http"
	"sort"
	"strings"
	"time"
)

//go:embed dashboard.html
var dashboardHTML string

type dbProvider interface {
	DB() *sql.DB
}

type dashboardSnapshot struct {
	GeneratedAt     string                  `json:"generated_at"`
	Version         string                  `json:"version"`
	Mode            string                  `json:"mode"`
	Commit          string                  `json:"commit"`
	Counts          dashboardCounts         `json:"counts"`
	LatestTick      dashboardTick           `json:"latest_tick"`
	Pools           []dashboardPool         `json:"pools"`
	Positions       []dashboardPosition     `json:"positions"`
	ClosedPositions []dashboardPosition     `json:"closed_positions"`
	Transactions    []dashboardTransaction  `json:"transactions"`
	PositionMarks   []dashboardPositionMark `json:"position_marks"`
	MarkSeries      []dashboardMarkPoint    `json:"mark_series"`
	ExitDecisions   []dashboardExitDecision `json:"exit_decisions"`
	ExitActions     []dashboardExitAction   `json:"exit_actions"`
	RecentScores    []dashboardScore        `json:"recent_scores"`
	Decisions       []dashboardDecision     `json:"decisions"`
	Warnings        []string                `json:"warnings"`
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
	mux.HandleFunc("/", app.dashboardAuth(app.handleDashboard))
	mux.HandleFunc("/dashboard", app.dashboardAuth(app.handleDashboard))
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

	return snapshot, nil
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
		SELECT position_id, pool_id, status, source, mark_time, hold_minutes,
		       valuation_usd, fee_usd, il_usd, net_pnl_usd,
		       current_tvl_usd, current_vol24h_usd, price_change_pct
		FROM (
			SELECT DISTINCT ON (position_id)
				position_id, pool_id, status, source, mark_time, hold_minutes,
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
